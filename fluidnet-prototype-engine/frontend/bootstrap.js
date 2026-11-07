// The browser owns module ordering. Report initialization failure in the existing page.
try {
  const {startStudio} = await import('./studio.js');
  startStudio();
} catch (error) {
  console.error('FluidNet initialization failed', error);
  const page = document.getElementById('page');
  if (page) {
    const message = document.createElement('p');
    message.setAttribute('role', 'alert');
    message.textContent = '工作台加载失败，请刷新重试。' + (error?.message || String(error));
    page.replaceChildren(message);
  }
}
