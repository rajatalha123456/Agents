interface BadgeProps {
  tone: 'neutral' | 'warning' | 'success' | 'danger'
  children: React.ReactNode
}

const TONE_CLASSES: Record<BadgeProps['tone'], string> = {
  neutral: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  warning: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
  success: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300',
  danger: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300',
}

export function Badge({ tone, children }: BadgeProps) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${TONE_CLASSES[tone]}`}>
      {children}
    </span>
  )
}
