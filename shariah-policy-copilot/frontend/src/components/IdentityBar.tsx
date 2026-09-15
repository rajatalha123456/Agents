import { useIdentity } from '../context/IdentityContext'
import { ROLES } from '../api/types'

export function IdentityBar() {
  const { identity, setUserId, setRole } = useIdentity()

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 bg-white px-4 py-2 text-sm dark:border-slate-800 dark:bg-slate-900">
      <span className="font-medium text-slate-500 dark:text-slate-400">Acting as</span>
      <label className="flex items-center gap-1.5">
        <span className="text-slate-500 dark:text-slate-400">User ID</span>
        <input
          aria-label="User ID"
          value={identity.userId}
          onChange={(e) => setUserId(e.target.value)}
          className="w-32 rounded border border-slate-300 bg-white px-2 py-1 text-slate-900 focus:border-emerald-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
        />
      </label>
      <label className="flex items-center gap-1.5">
        <span className="text-slate-500 dark:text-slate-400">Role</span>
        <select
          aria-label="Role"
          value={identity.role}
          onChange={(e) => setRole(e.target.value as (typeof ROLES)[number])}
          className="rounded border border-slate-300 bg-white px-2 py-1 text-slate-900 focus:border-emerald-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
        >
          {ROLES.map((role) => (
            <option key={role} value={role}>
              {role}
            </option>
          ))}
        </select>
      </label>
      <span className="ml-auto text-xs text-slate-400 dark:text-slate-500">
        Dev stub auth — Basic admin/admin + role header (app/utils/security.py)
      </span>
    </div>
  )
}
