import { useState, type ComponentProps, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { TabsContent as ShadcnTabsContent } from "./tabs";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "./collapsible";

export { Button } from "./button";
export { Switch } from "./switch";
export { Tabs, TabsList, TabsTrigger } from "./tabs";

export function Scene({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  const reduced = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={{ opacity: reduced ? 1 : 0, y: reduced ? 0 : 5 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduced ? 0 : 0.2, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
}

export function TabsContent({
  children,
  ...props
}: ComponentProps<typeof ShadcnTabsContent>) {
  return (
    <ShadcnTabsContent {...props}>
      <Scene>{children}</Scene>
    </ShadcnTabsContent>
  );
}

export function Disclosure({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const reduced = useReducedMotion();
  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className="mt-4 border-t border-border"
    >
      <CollapsibleTrigger className="flex min-h-11 w-full items-center justify-between gap-3 py-3 text-left text-sm font-medium text-muted-foreground transition-colors hover:text-teal-dark focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring">
        {title}
        <motion.span
          animate={{ rotate: open ? 180 : 0 }}
          transition={{ duration: reduced ? 0 : 0.18 }}
        >
          <ChevronDown size={16} aria-hidden="true" />
        </motion.span>
      </CollapsibleTrigger>
      <AnimatePresence initial={false}>
        {open && (
          <CollapsibleContent forceMount asChild>
            <motion.div
              initial={{
                height: reduced ? "auto" : 0,
                opacity: reduced ? 1 : 0,
              }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: reduced ? "auto" : 0, opacity: 0 }}
              transition={{ duration: reduced ? 0 : 0.18 }}
              className="overflow-hidden"
            >
              <div className="pb-4 text-sm leading-7 text-muted-foreground [&_p+p]:mt-2">
                {children}
              </div>
            </motion.div>
          </CollapsibleContent>
        )}
      </AnimatePresence>
    </Collapsible>
  );
}
