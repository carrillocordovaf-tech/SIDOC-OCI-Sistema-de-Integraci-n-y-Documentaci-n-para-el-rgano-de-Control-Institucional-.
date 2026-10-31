try { document.documentElement.dataset.theme = localStorage.getItem('sidoc-theme') === 'dark' ? 'dark' : 'light'; } catch { document.documentElement.dataset.theme = 'light'; }
