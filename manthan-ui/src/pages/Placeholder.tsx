import { motion } from "motion/react";
import { Sparkles } from "lucide-react";
import type { ReactNode } from "react";
import { Card, CardBody } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";

interface PlaceholderProps {
  title: string;
  description: string;
  comingSoon?: boolean;
  hint?: ReactNode;
}

export function Placeholder({
  title,
  description,
  comingSoon,
  hint,
}: PlaceholderProps) {
  return (
    <div className="px-6 py-6 max-w-5xl mx-auto">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
      >
        <div className="mb-6">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl md:text-3xl font-medium tracking-tight">
              {title}
            </h1>
            {comingSoon && <Badge tone="warning">Coming soon</Badge>}
          </div>
          <p className="mt-1.5 text-sm text-white/55">{description}</p>
        </div>

        <Card>
          <CardBody className="py-16 flex flex-col items-center text-center max-w-md mx-auto">
            <div className="h-14 w-14 rounded-2xl bg-white/[0.04] inline-flex items-center justify-center mb-5">
              <Sparkles className="h-6 w-6 text-white/55" />
            </div>
            <h2 className="text-lg font-medium">Wired, awaiting backend</h2>
            <p className="mt-2 text-sm text-white/55 leading-relaxed">
              The route exists, the design is locked. The data wires in
              when Manthan's backend ships this surface.
            </p>
            {hint && (
              <div className="mt-4 text-[12px] text-white/45 leading-relaxed">
                {hint}
              </div>
            )}
          </CardBody>
        </Card>
      </motion.div>
    </div>
  );
}
