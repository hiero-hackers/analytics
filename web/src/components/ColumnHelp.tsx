import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { InfoIcon } from 'lucide-react';
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover';

interface ColumnHelpProps {
  label: string;
  description?: string;
}

export function ColumnHelp({ label, description }: ColumnHelpProps) {
  const [open, setOpen] = useState(false);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild aria-label={`About ${label}`}>
        <Button variant="ghost" size="icon" className="h-4 w-4 shrink-0" aria-hidden="true">
          <InfoIcon aria-hidden="true" className="size-3.5" />
        </Button>
      </PopoverTrigger>

      <PopoverContent sideOffset={4} align="end">
        <p className="text-sm/-relaxed">{description}</p>
      </PopoverContent>
    </Popover>
  );
}
