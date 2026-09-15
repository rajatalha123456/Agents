import type { CSSProperties, ReactNode } from "react";

export function Card({ children, className = "", hover = false, style }: { children: ReactNode; className?: string; hover?: boolean; style?: CSSProperties }) {
  return <div className={`app-card ${hover ? "app-card-hover" : ""} ${className}`} style={style}>{children}</div>;
}

export function CardHeader({ title, action }: { title: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex items-center justify-between px-5 py-4 border-b" style={{ borderColor: "var(--hairline)" }}>
      <h2 className="font-semibold text-[15px]" style={{ color: "var(--ink-primary)" }}>{title}</h2>
      {action}
    </div>
  );
}

export function CardBody({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`px-5 py-4 ${className}`}>{children}</div>;
}
