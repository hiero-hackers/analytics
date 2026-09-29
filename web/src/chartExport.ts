/**
 * Saving a printed chart's sheet as a file, drawn in the browser without the
 * print dialog (so no browser header, footer or URL): a PNG or JPG image of the
 * page, or a PDF of its pages. The sheet is rendered once, at print resolution,
 * then laid on paper with the same margins as the printout.
 */

import {
  contentBox,
  MARGIN,
  PAPERS,
  paperBox,
  PX_PER_MM,
  type Orientation,
  type Paper,
} from './chartPrint';

export type FileFormat = 'png' | 'jpg' | 'pdf';

export const FORMATS: { format: FileFormat; label: string }[] = [
  { format: 'pdf', label: 'PDF' },
  { format: 'png', label: 'PNG' },
  { format: 'jpg', label: 'JPG' },
];

/** 3 × 96 = 288 dots per inch: sharp on paper, and at any zoom on screen. */
const SCALE = 3;
/** Keep every canvas side well inside what each browser can allocate. */
const MAX_SIDE = 16_000;
const PAPER_WHITE = '#ffffff';
const PT_PER_MM = 72 / 25.4;

const sameOrigin = (url: string) =>
  url.startsWith('data:') || new URL(url, location.href).origin === location.origin;

/** The sheet drawn at `scale`: the browser's own layout, rasterised via SVG. */
async function drawSheet(sheet: HTMLElement, scale: number) {
  const { domToCanvas } = await import('modern-screenshot');
  return domToCanvas(sheet, {
    // Its layout size: the preview scales the sheet on screen, the file must not.
    width: sheet.offsetWidth,
    height: sheet.offsetHeight,
    scale,
    backgroundColor: PAPER_WHITE,
    // Avatars are third-party images the page policy does not let a script
    // read; they are left out, and the initials drawn beneath them stand in.
    filter: (node) =>
      !(node instanceof HTMLImageElement && !sameOrigin(node.currentSrc || node.src)),
  });
}

function blank(width: number, height: number) {
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(width);
  canvas.height = Math.round(height);
  const context = canvas.getContext('2d')!;
  context.fillStyle = PAPER_WHITE;
  context.fillRect(0, 0, canvas.width, canvas.height);
  return { canvas, context };
}

/**
 * The sheet laid on paper: one tall image (`single`), or one canvas per page,
 * each continuing where the last page's printable area ended.
 */
async function layOut(sheet: HTMLElement, paper: Paper, orientation: Orientation, single: boolean) {
  const page = paperBox(paper, orientation);
  const content = contentBox(paper, orientation);
  const pageHeight = page.height * PX_PER_MM;
  const sheetHeight = sheet.offsetHeight + 2 * MARGIN * PX_PER_MM;
  const tallest = single ? Math.max(pageHeight, sheetHeight) : pageHeight;
  const scale = Math.min(SCALE, MAX_SIDE / tallest, MAX_SIDE / (page.width * PX_PER_MM));
  const drawn = await drawSheet(sheet, scale);
  const margin = MARGIN * PX_PER_MM * scale;
  const width = page.width * PX_PER_MM * scale;
  if (single) {
    const { canvas, context } = blank(width, tallest * scale);
    context.drawImage(drawn, margin, margin);
    return [canvas];
  }
  const slice = content.height * PX_PER_MM * scale;
  const count = Math.max(1, Math.ceil(drawn.height / slice - 0.001));
  return Array.from({ length: count }, (_, index) => {
    const { canvas, context } = blank(width, pageHeight * scale);
    const top = index * slice;
    const height = Math.min(slice, drawn.height - top);
    context.drawImage(drawn, 0, top, drawn.width, height, margin, margin, drawn.width, height);
    return canvas;
  });
}

const encoder = new TextEncoder();

async function deflate(bytes: Uint8Array) {
  // zlib-wrapped, which is exactly PDF's FlateDecode.
  const stream = new Blob([bytes as BlobPart])
    .stream()
    .pipeThrough(new CompressionStream('deflate'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

/** A canvas as 8-bit RGB samples, the layout a PDF image stream expects. */
function rgb(canvas: HTMLCanvasElement) {
  const { data } = canvas.getContext('2d')!.getImageData(0, 0, canvas.width, canvas.height);
  const samples = new Uint8Array(canvas.width * canvas.height * 3);
  for (let pixel = 0, out = 0; pixel < data.length; pixel += 4) {
    samples[out++] = data[pixel];
    samples[out++] = data[pixel + 1];
    samples[out++] = data[pixel + 2];
  }
  return samples;
}

/** A PDF text string, as UTF-16 so titles keep their dashes and accents. */
function pdfText(text: string) {
  let hex = '';
  for (let index = 0; index < text.length; index++) {
    hex += text.charCodeAt(index).toString(16).padStart(4, '0');
  }
  return `<FEFF${hex}>`;
}

/**
 * A minimal PDF: one losslessly compressed image per page, at the paper's exact
 * size. Hand-written rather than a library, since that is all it needs to hold.
 */
export async function pagesToPdf(
  pages: HTMLCanvasElement[],
  size: { width: number; height: number },
  title: string,
) {
  const width = (size.width * PT_PER_MM).toFixed(2);
  const height = (size.height * PT_PER_MM).toFixed(2);
  const chunks: Uint8Array[] = [];
  const offsets: number[] = [];
  let length = 0;
  const push = (part: string | Uint8Array) => {
    const bytes = typeof part === 'string' ? encoder.encode(part) : part;
    chunks.push(bytes);
    length += bytes.length;
  };
  const object = (id: number, body: string, stream?: Uint8Array) => {
    offsets[id] = length;
    push(`${id} 0 obj\n${body}\n`);
    if (stream) {
      push('stream\n');
      push(stream);
      push('\nendstream\n');
    }
    push('endobj\n');
  };

  // 1 catalog, 2 page tree, 3 info; then page, contents and image per page.
  const pageId = (index: number) => 4 + index * 3;
  push('%PDF-1.4\n%âãÏÓ\n');
  object(1, '<< /Type /Catalog /Pages 2 0 R >>');
  object(
    2,
    `<< /Type /Pages /Count ${pages.length} /Kids [${pages.map((_, i) => `${pageId(i)} 0 R`).join(' ')}] >>`,
  );
  object(3, `<< /Title ${pdfText(title)} /Producer ${pdfText('Hiero analytics')} >>`);
  for (const [index, page] of pages.entries()) {
    const id = pageId(index);
    object(
      id,
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${width} ${height}] /Resources << /XObject << /Im0 ${id + 2} 0 R >> >> /Contents ${id + 1} 0 R >>`,
    );
    const drawing = encoder.encode(`q ${width} 0 0 ${height} 0 0 cm /Im0 Do Q`);
    object(id + 1, `<< /Length ${drawing.length} >>`, drawing);
    const image = await deflate(rgb(page));
    object(
      id + 2,
      `<< /Type /XObject /Subtype /Image /Width ${page.width} /Height ${page.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length ${image.length} >>`,
      image,
    );
  }
  const count = pageId(pages.length);
  const xref = length;
  push(`xref\n0 ${count}\n0000000000 65535 f \n`);
  for (let id = 1; id < count; id++) push(`${String(offsets[id]).padStart(10, '0')} 00000 n \n`);
  push(`trailer\n<< /Size ${count} /Root 1 0 R /Info 3 0 R >>\nstartxref\n${xref}\n%%EOF\n`);
  return new Blob(chunks as BlobPart[], { type: 'application/pdf' });
}

const toBlob = (canvas: HTMLCanvasElement, type: string) =>
  new Promise<Blob>((resolve, reject) =>
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error('Image encoding failed'))),
      type,
      0.92,
    ),
  );

/** The file for one sheet: its pages as a PDF, or the page as one image. */
export async function exportSheet(
  sheet: HTMLElement,
  {
    format,
    paper,
    orientation,
    title,
  }: { format: FileFormat; paper: Paper; orientation: Orientation; title: string },
) {
  await document.fonts?.ready;
  if (format === 'pdf') {
    const pages = await layOut(sheet, paper, orientation, false);
    return pagesToPdf(pages, paperBox(paper, orientation), title);
  }
  const [image] = await layOut(sheet, paper, orientation, true);
  return toBlob(image, format === 'png' ? 'image/png' : 'image/jpeg');
}

/** "Role activity" on A4 landscape → role-activity-a4-landscape.pdf */
export function exportName(
  title: string,
  paper: Paper,
  orientation: Orientation,
  format: FileFormat,
) {
  const slug =
    title
      .toLowerCase()
      .normalize('NFKD')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '') || 'chart';
  return `${slug}-${PAPERS[paper].label.toLowerCase()}-${orientation}.${format}`;
}

export function saveBlob(blob: Blob, filename: string) {
  const anchor = document.createElement('a');
  anchor.href = URL.createObjectURL(blob);
  anchor.download = filename;
  anchor.click();
  // Some browsers read the URL after click returns; release it once they have.
  setTimeout(() => URL.revokeObjectURL(anchor.href), 1000);
}
