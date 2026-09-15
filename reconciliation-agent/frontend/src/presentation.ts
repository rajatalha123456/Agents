/** User-facing language and exact decimal display, shared across screens. */
export const PAGE_TITLES: Record<string, string> = {
  Overview: 'Dashboard', Imports: 'Upload Files', 'Break queue': 'Review differences',
  'Agent activity': 'Agent history', 'Period close': 'Finish month',
  'Universe board': 'Account overview', 'Match canvas': 'Match manually',
  'Approval queue': 'All approvals', Ageing: 'Older differences',
  'Journal drafts': 'Journal drafts', 'Certification pack': 'Evidence report',
  'Audit trail': 'Audit history', 'Rule packs': 'Matching rules',
  'Model governance': 'Model quality', Pilot: 'Pilot setup', Admin: 'Advanced settings', Settings: 'Workspace settings',
};
export const ROLE_TITLES: Record<string, string> = {MAKER:'Prepare & investigate', CHECKER:'Review & approve', CERTIFIER:'Review month-end'};
export const STATUS_TITLES: Record<string, string> = {
  OPEN:'Needs checking', TRIAGED:'Under investigation', PROPOSED:'Ready to review',
  UNDER_REVIEW:'In review', ACTION_PENDING:'Evidence needed', APPROVED:'Approved',
  REJECTED:'Rejected', RETURNED:'More information needed', CLOSED:'Resolved', RESOLVED:'Resolved',
  CARRIED_FORWARD:'Carried to next month', COMMITTED:'Ready to check', HELD:'File needs attention',
  CERTIFIED:'Month completed', MATCHED:'Matched', COMPLETED:'Completed',
};
export function friendlyStatus(value:string) {return STATUS_TITLES[value]??value.toLowerCase().replaceAll('_',' ').replace(/^./, s=>s.toUpperCase());}
const SCALE=100_000_000n;
export function decimalUnits(value:string):bigint {
  if(!/^-?\d+(?:\.\d{0,8})?$/.test(value)) throw new Error('Invalid decimal amount');
  const negative=value.startsWith('-');
  const [whole,fraction='']=(negative?value.slice(1):value).split('.');
  const units=BigInt(whole)*SCALE+BigInt(fraction.padEnd(8,'0'));
  return negative?-units:units;
}
export function decimalString(units:bigint):string {
  const value=units<0n?-units:units;
  return `${units<0n?'-':''}${value/SCALE}.${String(value%SCALE).padStart(8,'0')}`;
}
export function money(amount:string, currency='USD'):string {
  try {
    const units=decimalUnits(amount);
    const abs=units<0n?-units:units;
    const fraction=String(abs%SCALE).padStart(8,'0').replace(/0+$/,'').padEnd(2,'0');
    const formatted=new Intl.NumberFormat('en-US',{style:'currency',currency,minimumFractionDigits:2}).formatToParts(abs/SCALE).map(p=>p.type==='fraction'?fraction:p.value).join('');
    return `${units<0n?'-':''}${formatted}`;
  } catch { return `${currency} ${amount}`; }
}
export const sourceName=(side:string)=>side==='SOURCE_A'?'Bank records':'Accounting records';
