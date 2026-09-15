import { test, expect, type Page } from '@playwright/test';

async function login(page:Page, user='analyst') {
  await page.getByLabel('Username').fill(user);
  await page.getByLabel('Password').fill(`${user}-demo-pass`);
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await expect(page.locator('.simple-dashboard')).toBeVisible();
}
test('clear dashboard, uploads, agent check, human review and mobile', async ({page})=>{
  const errors:string[]=[]; page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/'); await login(page);
  await expect(page.getByRole('heading',{name:'Automated Record Review'})).toBeVisible();
  await expect(page.getByRole('navigation',{name:'Main navigation'}).getByRole('button')).toHaveCount(5);
  await expect(page.getByRole('navigation',{name:'More tools',exact:true})).toHaveCount(0);
  await page.getByLabel('Reconciliation period').fill('2099-01');
  for(const [side,name,extra] of [['SOURCE_A','bank.csv',''],['SOURCE_B','ledger.csv','25,USD,CR,2099-01-02,FEE1,Service fee\n']]) {
    await page.locator('.heading-actions').getByRole('button',{name:'Upload Files'}).click();
    const dialog=page.getByRole('dialog');
    await expect(dialog.getByLabel('Expected row count (optional)')).not.toBeVisible();
    await dialog.getByLabel('These records are from').selectOption(side);
    await dialog.getByLabel('Account name').fill('Operating');
    await dialog.getByLabel('Source file').setInputFiles({name,mimeType:'text/csv',buffer:Buffer.from('amount,currency,direction,value_date,reference,description\n10,USD,CR,2099-01-01,R1,Customer payment\n'+extra)});
    await expect(dialog.getByLabel('File type')).toHaveValue('CSV');
    await dialog.getByRole('button',{name:'Upload and check file'}).click();
    await expect(dialog).not.toBeVisible();
    await page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name:'Dashboard'}).click();
  }
  await page.getByRole('button',{name:'Check Records',exact:true}).click();
  await expect(page.getByRole('heading',{name:'1 recommendation is ready for review'})).toBeVisible({timeout:30000});
  await page.screenshot({path:'test-results/dashboard-desktop.png',fullPage:true});
  await page.locator('.next-step-card').getByRole('button',{name:'Review Differences',exact:true}).click();
  await page.getByRole('button',{name:/^Review difference /}).first().click();
  await expect(page.getByRole('heading',{name:'Recommended next step'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Approve next step'})).toBeDisabled();
  await page.keyboard.press('Escape');
  await page.getByRole('button',{name:'Sign out'}).click();
  await login(page,'reviewer');
  await page.getByLabel('Reconciliation period').fill('2099-01');
  await page.locator('.next-step-card').getByRole('button',{name:'Review Differences',exact:true}).click();
  await page.getByRole('button',{name:/^Review difference /}).first().click();
  await page.getByLabel('Decision reason').fill('Checked the source evidence and approved the follow-up.');
  await page.getByRole('button',{name:'Approve next step'}).click();
  await expect(page.getByLabel('External action / evidence reference')).toBeVisible();
  await page.keyboard.press('Escape');
  await page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name:'Dashboard'}).click();
  await page.getByRole('button',{name:'More tools',exact:true}).click();
  for(const name of ['Account overview','Match manually','All approvals','Older differences','Journal drafts','Evidence report','Audit history','Matching rules','Model quality','Pilot setup','Advanced settings']){
    await page.getByRole('navigation',{name:'More tools',exact:true}).getByRole('button',{name,exact:true}).click();
    await expect(page.locator('main h1')).toHaveText(name);
    await expect(page.getByRole('alert')).toHaveCount(0);
  }
  await page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name:'Dashboard'}).click();
  await page.setViewportSize({width:390,height:844});
  await expect(page.getByRole('navigation',{name:'Main navigation'})).toBeHidden();
  await page.screenshot({path:'test-results/dashboard-mobile.png',fullPage:true,animations:'disabled'});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  await page.getByRole('button',{name:'Toggle navigation'}).click();
  await page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name:'Upload Files'}).click();
  await expect(page.locator('main h1')).toHaveText('Upload Files');
  expect(errors).toEqual([]);
});

test('upload detects Excel and reveals optional mappings on request',async({page})=>{
  await page.goto('/');await login(page);
  await page.locator('.heading-actions').getByRole('button',{name:'Upload Files'}).click();
  const dialog=page.getByRole('dialog');
  await dialog.getByLabel('Source file').setInputFiles({name:'ledger.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:Buffer.from('format detection only')});
  await expect(dialog.getByLabel('File type')).toHaveValue('EXCEL');
  await expect(dialog.getByLabel('Expected row count (optional)')).not.toBeVisible();
  await dialog.getByText('Column names & optional checks',{exact:true}).click();
  await expect(dialog.getByLabel('Expected row count (optional)')).toBeVisible();
  await page.keyboard.press('Escape'); await expect(dialog).not.toBeVisible();
});
