export function el(tag, attributes = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) {
    if (key.startsWith("on")) node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (value !== undefined && value !== null) {
      if (key in node) node[key] = value;
      else node.setAttribute(key, value);
    }
  }
  for (const child of children.flat()) if (child !== undefined && child !== null) node.append(child);
  return node;
}

export function button(label, action, className = "") {
  return el("button", { type: "button", class: className, text: label, onclick: action });
}

export function select(value, options, action, attributes = {}) {
  const node = el("select", { ...attributes, onchange: event => action(event.target.value) },
    options.map(option => el("option", { value: option.value, text: option.label })));
  node.value = value;
  return node;
}

export function field(label, input, hint) {
  return el("label", { class: "capi-field" }, el("span", { text: label }), input,
    hint ? el("small", { text: hint }) : null);
}

export function readFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}
