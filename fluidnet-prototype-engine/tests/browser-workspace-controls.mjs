import {expect} from '@playwright/test';

// Follow the same disclosures as a user, leaving all physics assertions in each case.
export async function workspaceControl(page,selector){
  const control=page.locator(selector).first();
  if(await control.isVisible())return control;
  if(selector.includes('cs-create')){
    await page.locator('[data-action="project-examples"]').first().click();
  }else{
    const disclosure=control.locator('xpath=ancestor::details[@data-workspace-menu]');
    await expect(disclosure).toHaveCount(1);
    if(!await disclosure.getAttribute('open').then(value=>value!==null))await disclosure.locator('summary').click();
  }
  await expect(control).toBeVisible();
  return control;
}

export async function createProjectExample(page,action){
  const example=await workspaceControl(page,`[data-action="${action}"]`);
  await example.click();
}
