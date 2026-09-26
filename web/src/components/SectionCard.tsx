/**
 * The chrome every content card shares — tables, bespoke views and chart
 * galleries all render through this, so a change to the header, the actions
 * or the "data as of" treatment cannot apply to one kind and miss the others.
 *
 * A shadcn Card, collapsible as a whole: the header (title, description, size
 * badge, collapse toggle) stays visible, the actions, content and freshness
 * footer fold away. The card is a labelled region and keeps its `id`, which
 * shared `#widget=` links scroll to and briefly flash (App adds `flash`).
 */

import { useId, useState, type ReactNode } from 'react';
import { ChevronDownIcon } from 'lucide-react';
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

export function SectionCard({
  id,
  title,
  badge,
  description,
  generatedAt,
  stale,
  actions,
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
  children: ReactNode;
}) {
  const titleId = useId();
  const [open, setOpen] = useState(true);

  return (
    <Collapsible asChild open={open} onOpenChange={setOpen}>
      <Card
        id={id}
        role="region"
        aria-labelledby={titleId}
        // scroll-mt: land below the sticky header. [&.flash]: the shared-link
        // highlight, toggled as a class by App's jump effect.
        className="mb-5 scroll-mt-(--jump-h) transition-colors duration-500 [&.flash]:bg-(--flash)"
      >
        <CardHeader>
          <CardTitle>
            <h2 id={titleId} className="text-base font-semibold tracking-tight">
              {title}
            </h2>
          </CardTitle>
          <CardDescription className="max-w-[80ch] group-data-[state=closed]/card:hidden">
            {description}
          </CardDescription>
          <CardAction className="flex items-center gap-1.5">
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
          {/* Actions wrap onto as many rows as they need — on a phone three
              buttons no longer push the page sideways. */}
          {actions && (
            <CardContent className="flex flex-wrap items-center gap-2">{actions}</CardContent>
          )}
          <CardContent>{children}</CardContent>
          {generatedAt && (
            <CardFooter className="border-t text-muted-foreground">
              <p className={stale ? 'font-medium text-warn-ink' : undefined}>
                data as of {stamp(generatedAt)}
                {stale ? ' — older than the scheduled refresh' : ''}
              </p>
            </CardFooter>
          )}
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}
