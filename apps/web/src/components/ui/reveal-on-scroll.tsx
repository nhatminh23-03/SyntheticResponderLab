"use client";

import { PropsWithChildren } from "react";
import { motion } from "framer-motion";

type RevealOnScrollProps = PropsWithChildren<{
  delay?: number;
  className?: string;
  amount?: number;
}>;

export function RevealOnScroll({
  children,
  delay = 0,
  className,
  amount = 0.24,
}: RevealOnScrollProps) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 28 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount }}
      transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1], delay }}
    >
      {children}
    </motion.div>
  );
}
