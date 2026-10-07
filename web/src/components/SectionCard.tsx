/**
 * The collapsible chrome every content card shares (tables, bespoke views, chart
 * galleries), so header, actions and "data as of" stay consistent. The card keeps
 * its `id` for shared `#widget=` links, which scroll to it and flash it.
 */

import { useId, useState, type ReactNode } from 'react';
import { ChevronDownIcon, Clock3Icon } from 'lucide-react';
import { cn } from 'cn';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { stamp } from '../format';
import { usePrintMode } from '../printContext';

export function SectionCard({
  id,
  title,
  badge,
  description,
  generatedAt,
  stale,
  actions,
  headerActions,
  children,
}: {
  id?: string;
  title: string;
  /** Size of what the card holds ("3 rows", "158 HIPs"); omitted for chart galleries. */
  badge?: ReactNode;
  description: string;
  generatedAt?: string;
  stale?: boolean;
  actions?: ReactNode;
  /** Small actions beside the title (a chart card's Copy link), instead of a row of their own. */
  headerActions?: ReactNode;
  children: ReactNode;
}) {
  const titleId = useId();
  const printing = usePrintMode();
  // Paper shows every card open; the reader's own collapse returns afterwards.
  const [open, setOpen] = useState(true);

  return (
    <Collapsible asChild open={printing || open} onOpenChange={setOpen}>
      <Card
        id={id}
        role="region"
        aria-labelledby={titleId}
        // scroll-mt clears the sticky header; App toggles `flash` on shared-link jumps.
        className="mb-6 rounded-xl shadow-xs [--card-spacing:--spacing(5)] scroll-mt-(--jump-h) transition-colors duration-500 [&.flash]:bg-(--flash)"
      >
        <CardHeader>
          <CardTitle>
            <h2 id={titleId} className="font-display text-[17px] font-semibold tracking-tight">
              {title}
            </h2>
          </CardTitle>
          <CardDescription className="max-w-[80ch] group-data-[state=closed]/card:hidden">
            {description}
          </CardDescription>
          <CardAction className="flex items-center gap-1.5">
            {headerActions}
            {badge !== undefined && (
              <Badge variant="secondary" className="tabular-nums">
                {badge}
              </Badge>
            )}
            <CollapsibleTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={open ? `Collapse ${title}` : `Expand ${title}`}
              >
                <ChevronDownIcon className="transition-transform group-data-[state=closed]/card:-rotate-90" />
              </Button>
            </CollapsibleTrigger>
          </CardAction>
        </CardHeader>
        <CollapsibleContent className="flex flex-col gap-(--card-spacing)">
          {actions && (
            <CardContent className="flex flex-wrap items-center gap-2">{actions}</CardContent>
          )}
          <CardContent>{children}</CardContent>
          {generatedAt && (
            <CardFooter className="border-t py-3 text-xs text-muted-foreground">
              <p className={cn('flex items-center gap-1.5', stale && 'font-medium text-warn-ink')}>
                <Clock3Icon aria-hidden="true" className="size-3.5" />
                Data as of {stamp(generatedAt)} UTC
                {stale ? ', older than the scheduled refresh' : ''}
              </p>
            </CardFooter>
          )}
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}
