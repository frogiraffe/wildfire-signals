// A single investigation workflow over existing verified archival studies.
// Navigation changes presentation only; it never alters evidence or source windows.
export const workspaceGroups = Object.freeze({
  overview:['controls-heading','unified-heading','annual-heading','historical-timeline-heading','evidence-compare-heading','historical-navigation-heading'],
  geography:['spatial-heading','historical-navigation-heading'],
  environment:['weather-heading'],
  validation:['spatial-heading','catalog-heading','standard-readiness-heading','sensitivity-heading','frap-heading','methods-heading'],
  all:[]
});
export function workspaceSelection(mode) {
  if (!Object.hasOwn(workspaceGroups,mode)) throw new Error('Unknown investigation view');
  return workspaceGroups[mode];
}
export function activateWorkspace(mode,sections) {
  const show=new Set(workspaceSelection(mode));
  for (const section of sections) {
    const heading=section.getAttribute('aria-labelledby');
    section.hidden=mode!=='all' && !show.has(heading);
  }
}
export function mountWorkspace(root=document) {
  const menu=root.getElementById('workspace-mode');
  const sections=[...root.querySelectorAll('.analytics-main > section.analytics-card[aria-labelledby]')];
  const note=root.getElementById('workspace-view-note');
  const buttons=[...root.querySelectorAll('[data-workspace-target]')];
  const update=mode=>{
    activateWorkspace(mode,sections);
    menu.value=mode;
    for(const button of buttons){
      const active=button.dataset.workspaceTarget===mode;
      button.setAttribute('aria-pressed',String(active));
    }
    const descriptions={
      all:'All research panels are visible. Each study retains its own date range and acquisition limitations.',
      overview:'Annual archives, multi-year comparisons and study selection. Spatial grid data remains a full-period aggregate.',
      geography:'Published 0.01° satellite research cells and their provenance; not true burn perimeters.',
      environment:'Historical station context only; station conditions are not necessarily those at satellite pixels.',
      validation:'Inspect coverage, independent agency evidence and model eligibility limitations.'
    };
    note.textContent=descriptions[mode];
  };
  menu.addEventListener('change',()=>update(menu.value));
  for(const button of buttons)button.addEventListener('click',()=>update(button.dataset.workspaceTarget));
  update('all');
  // Deep links remain functional even when the targeted group is currently hidden.
  const revealHash=()=>{
    const id=decodeURIComponent(location.hash.slice(1));
    if(!id)return;
    const target=root.getElementById(id);
    const section=target?.closest('.analytics-main > section[aria-labelledby]');
    if(section?.hidden)update('all');
  };
  root.defaultView?.addEventListener('hashchange',revealHash);
  revealHash();
}
