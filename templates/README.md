### templates/README.md

```markdown
# templates/

Contains a single file: `index.html`, which serves as the app's entire page shell. The layout includes a sidebar (featuring address search, timing toggles, mode checkboxes, plan/reset buttons, the results container, and an admin data-refresh card), the main map `<div>`, and a toast-notification container. 

There is no inline JS or CSS, and no dead markup. All behavior is handled in [static/js/map.js](../static/js/map.js) and all styling is in [static/css/style.css](../static/css/style.css). This HTML file strictly defines the DOM structure. Element IDs and classes like `#results`, `#plan-trip-btn`, and `.mode-check` act as the contract between the markup and the frontend assets.