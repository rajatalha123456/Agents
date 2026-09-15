const VARIANTS = {
  primary:
    "bg-indigo-600 text-white shadow-sm hover:bg-indigo-700 disabled:bg-indigo-300 disabled:shadow-none",
  secondary:
    "bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 hover:border-slate-400 disabled:text-slate-400 disabled:hover:bg-white",
  danger:
    "bg-rose-50 text-rose-700 border border-rose-200 hover:bg-rose-100 disabled:text-rose-300",
  ghost: "text-slate-500 hover:text-slate-800 hover:bg-slate-100",
};

export default function Button({ variant = "secondary", className = "", ...props }) {
  return (
    <button
      className={
        "inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-sm font-medium " +
        "transition-colors disabled:cursor-not-allowed " +
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 focus-visible:ring-offset-1 " +
        VARIANTS[variant] +
        " " +
        className
      }
      {...props}
    />
  );
}
