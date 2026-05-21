function formSnapshot(form) {
  return Array.from(form.elements)
    .filter((element) => element.name && !element.disabled)
    .map((element) => `${element.name}=${element.value}`)
    .join("&");
}

function wireDirtyForms() {
  document.querySelectorAll(".js-dirty-form").forEach((form) => {
    const submitButton = form.querySelector('button[type="submit"]');
    if (!submitButton) {
      return;
    }

    const initialSnapshot = formSnapshot(form);
    const updateState = () => {
      submitButton.disabled = formSnapshot(form) === initialSnapshot;
    };

    form.addEventListener("input", updateState);
    form.addEventListener("change", updateState);
    updateState();
  });
}

document.addEventListener("DOMContentLoaded", wireDirtyForms);
