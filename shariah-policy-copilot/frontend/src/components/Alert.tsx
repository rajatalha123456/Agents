interface AlertProps {
  variant: 'error' | 'info' | 'success'
  children: React.ReactNode
}

const VARIANT_CLASSES: Record<AlertProps['variant'], string> = {
  error: 'border-red-300 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200',
  info: 'border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-200',
  success:
    'border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200',
}

export function Alert({ variant, children }: AlertProps) {
  return (
    <div role="alert" className={`rounded-md border px-3 py-2 text-sm ${VARIANT_CLASSES[variant]}`}>
      {children}
    </div>
  )
}
