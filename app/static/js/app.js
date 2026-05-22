function formSnapshot(form) {
  return Array.from(form.elements)
    .filter((element) => element.name && !element.disabled)
    .map((element) => `${element.name}=${element.value}`)
    .join("&");
}

function isFormEmpty(form) {
  return Array.from(form.elements)
    .filter((element) => element.name && !element.disabled)
    .every((element) => !element.value.trim());
}

function updateFormEmptyState(form) {
  const empty = isFormEmpty(form);
  form.dataset.empty = empty ? "true" : "false";
  form.querySelectorAll("[data-enable-when-empty]").forEach((element) => {
    element.disabled = !empty;
  });
}

function wireDirtyForms() {
  document.querySelectorAll(".js-dirty-form").forEach((form) => {
    const submitButton =
      form.querySelector('button[type="submit"]') ||
      (form.id ? document.querySelector(`button[form="${form.id}"]`) : null);

    const initialSnapshot = formSnapshot(form);
    const updateState = () => {
      const dirty = formSnapshot(form) !== initialSnapshot;
      form.dataset.dirty = dirty ? "true" : "false";
      const section = form.closest(".editable-section");
      const editing = section?.classList.contains("is-editing") ?? true;
      if (submitButton && !submitButton.dataset.alwaysEnabled) {
        submitButton.disabled = editing ? !dirty : false;
      }
      if (form.dataset.dirtyDisableSelector) {
        document
          .querySelectorAll(form.dataset.dirtyDisableSelector)
          .forEach((element) => {
            element.disabled = dirty;
          });
      }
      if (form.dataset.dirtyHideSelector) {
        document
          .querySelectorAll(form.dataset.dirtyHideSelector)
          .forEach((element) => {
            element.hidden = dirty;
          });
      }
    };

    form.addEventListener("input", updateState);
    form.addEventListener("change", updateState);
    form.updateDirtyState = updateState;
    updateState();
  });
}

function wireConfirmDeleteForms() {
  document.querySelectorAll(".js-confirm-delete").forEach((form) => {
    const deleteButton = form.querySelector('button[type="submit"]');
    if (!deleteButton) {
      return;
    }

    const originalText = deleteButton.textContent;
    let confirming = false;

    form.addEventListener("submit", (event) => {
      if (confirming) {
        return;
      }

      event.preventDefault();
      confirming = true;
      form.classList.add("confirming-delete");
      deleteButton.textContent = "Yes";

      const prompt = document.createElement("span");
      prompt.className = "confirm-delete-prompt";
      prompt.textContent = "Are you sure?";

      const cancelButton = document.createElement("button");
      cancelButton.type = "button";
      cancelButton.className = "ghost confirm-delete-cancel";
      cancelButton.textContent = "No";
      cancelButton.addEventListener("click", () => {
        confirming = false;
        form.classList.remove("confirming-delete");
        deleteButton.textContent = originalText;
        prompt.remove();
        cancelButton.remove();
      });

      form.prepend(prompt);
      form.append(cancelButton);
    });

    updateFormEmptyState(form);
  });
}

function wireEditSections() {
  document.querySelectorAll(".editable-section").forEach((section) => {
    const toggleButton = section.querySelector(".js-toggle-edit-section");
    if (!toggleButton) {
      return;
    }

    toggleButton.addEventListener("click", (event) => {
      event.preventDefault();
      const form = toggleButton.dataset.editSubmitForm
        ? document.getElementById(toggleButton.dataset.editSubmitForm)
        : null;

      if (section.classList.contains("is-editing")) {
        if (form?.dataset.dirty === "true") {
          form.requestSubmit();
          return;
        }
        section.classList.remove("is-editing");
        toggleButton.textContent = "Edit";
        form?.updateDirtyState?.();
        return;
      }

      const editing = section.classList.toggle("is-editing");
      if (toggleButton.dataset.editSubmitForm) {
        toggleButton.textContent = editing ? "Done" : "Edit";
      } else {
        toggleButton.textContent = editing ? "Done" : "Edit";
      }
      form?.updateDirtyState?.();
    });
  });
}

function wireStagedRemoveButtons() {
  document.querySelectorAll(".js-stage-remove").forEach((button) => {
    button.addEventListener("click", () => {
      const row = button.closest("[data-staged-row]");
      const field = row?.querySelector('[data-delete-field]');
      const form = button.closest("form");
      if (!row || !(field instanceof HTMLInputElement)) {
        return;
      }
      const deleted = field.value === "true";
      field.value = deleted ? "false" : "true";
      row.classList.toggle("is-staged-delete", !deleted);
      button.textContent = deleted ? "Remove" : "Undo";
      form?.updateDirtyState?.();
    });
  });
}

function createLineItemRow(values = {}, options = {}) {
  const prefix = options.prefix || "item";
  const includePrice = options.includePrice !== false;
  const row = document.createElement("div");
  row.className = options.rowClass || "line-item-builder-row";
  const fieldsClass = options.fieldsClass || "";
  row.innerHTML = `
    <input type="hidden" name="${prefix}_id" value="">
    <input type="hidden" name="${prefix}_delete" value="false">
    <div class="${fieldsClass}">
      <label>
        Name
        <input name="${prefix}_name" required placeholder="${options.namePlaceholder || "Greek yogurt"}">
      </label>
      <label>
        Qty
        <input name="${prefix}_quantity" inputmode="decimal" placeholder="${options.quantityPlaceholder || "2"}">
      </label>
      <label>
        Unit
        <input name="${prefix}_unit" placeholder="${options.unitPlaceholder || "cups"}">
      </label>
      ${
        includePrice
          ? `<label>
              Price
              <input name="${prefix}_price" inputmode="decimal" placeholder="5.99">
            </label>`
          : ""
      }
      <label>
        Notes
        <input name="${prefix}_notes" placeholder="${options.notesPlaceholder || "Brand, sale, substitute"}">
      </label>
      <button class="ghost js-remove-line-item" type="button">Remove</button>
    </div>
  `;
  row.querySelector(".js-remove-line-item").addEventListener("click", () => {
    const form = row.closest("form");
    row.remove();
    if (form) {
      updateFormEmptyState(form);
      form.updateDirtyState?.();
    }
  });
  row.querySelector(`[name="${prefix}_name"]`).value = values.name || "";
  row.querySelector(`[name="${prefix}_quantity"]`).value = values.quantity || "";
  row.querySelector(`[name="${prefix}_unit"]`).value = values.unit || "";
  if (includePrice) {
    row.querySelector(`[name="${prefix}_price"]`).value = values.price || "";
  }
  row.querySelector(`[name="${prefix}_notes"]`).value = values.notes || "";
  return row;
}

function wireLineItemBuilders() {
  document.querySelectorAll(".line-item-builder").forEach((builder) => {
    const addButton = builder.querySelector(".js-add-line-item");
    const rows = builder.querySelector("[data-line-item-rows]");
    if (!addButton || !rows) {
      return;
    }

    const options = {
      prefix: builder.dataset.fieldPrefix || "item",
      includePrice: builder.dataset.includePrice !== "false",
      rowClass: builder.dataset.rowClass || "line-item-builder-row",
      fieldsClass: builder.dataset.fieldsClass || "",
      namePlaceholder: builder.dataset.namePlaceholder,
      quantityPlaceholder: builder.dataset.quantityPlaceholder,
      unitPlaceholder: builder.dataset.unitPlaceholder,
      notesPlaceholder: builder.dataset.notesPlaceholder,
    };

    rows.querySelectorAll(".js-remove-line-item").forEach((button) => {
      button.addEventListener("click", () => {
        const row = button.closest(".line-item-builder-row, .recipe-ingredient-builder-row, .editable-row");
        const form = button.closest("form");
        row?.remove();
        if (form) {
          updateFormEmptyState(form);
          form.updateDirtyState?.();
        }
      });
    });

    addButton.addEventListener("click", () => {
      rows.append(createLineItemRow({}, options));
      const form = builder.closest("form");
      if (form) {
        updateFormEmptyState(form);
        form.updateDirtyState?.();
      }
    });
  });
}

function wireClearableForms() {
  document.querySelectorAll(".js-clearable-form").forEach((form) => {
    const clearButton = form.querySelector(".js-clear-form");
    const lineItemRows = form.querySelector("[data-line-item-rows]");
    if (!clearButton) {
      return;
    }

    let confirming = false;
    const originalText = clearButton.textContent;

    const resetClearState = () => {
      confirming = false;
      form.classList.remove("confirming-clear");
      clearButton.textContent = originalText;
      form.querySelector(".confirm-clear-prompt")?.remove();
      form.querySelector(".confirm-clear-yes")?.remove();
    };

    const clearForm = () => {
      form.reset();
      if (lineItemRows) {
        lineItemRows.innerHTML = "";
      }
      resetClearState();
      updateFormEmptyState(form);
    };

    form.addEventListener("input", () => updateFormEmptyState(form));
    form.addEventListener("change", () => updateFormEmptyState(form));

    clearButton.addEventListener("click", () => {
      if (confirming) {
        resetClearState();
        return;
      }
      if (isFormEmpty(form)) {
        return;
      }

      confirming = true;
      form.classList.add("confirming-clear");
      clearButton.textContent = "No";

      const prompt = document.createElement("span");
      prompt.className = "confirm-clear-prompt";
      prompt.textContent = "Are you sure?";

      const yesButton = document.createElement("button");
      yesButton.type = "button";
      yesButton.className = "confirm-clear-yes";
      yesButton.textContent = "Yes";
      yesButton.addEventListener("click", clearForm);

      clearButton.before(prompt);
      clearButton.before(yesButton);
    });

    updateFormEmptyState(form);
  });
}

function populatePurchaseFormFromReceipt(form, preview) {
  form.querySelector('[name="store"]').value = preview.merchant || "";
  form.querySelector('[name="total_amount"]').value = preview.total || "";

  const rows = form.querySelector("[data-line-item-rows]");
  if (rows) {
    rows.innerHTML = "";
    (preview.items || []).forEach((item) => {
      rows.append(createLineItemRow(item));
    });
  }

  updateFormEmptyState(form);
}

function wireReceiptUploads() {
  document.querySelectorAll(".add-purchase-form").forEach((form) => {
    const uploadButton = form.querySelector(".js-upload-receipt");
    const fileInput = form.querySelector(".js-receipt-file");
    const status = form.querySelector("[data-receipt-status]");
    if (!uploadButton || !fileInput) {
      return;
    }

    uploadButton.dataset.enableWhenEmpty = "true";
    updateFormEmptyState(form);

    uploadButton.addEventListener("click", () => {
      if (!isFormEmpty(form)) {
        return;
      }
      fileInput.click();
    });

    fileInput.addEventListener("change", async () => {
      const file = fileInput.files && fileInput.files[0];
      if (!file) {
        return;
      }

      if (status) {
        status.textContent = "Parsing receipt...";
        status.hidden = false;
      }
      uploadButton.disabled = true;

      const formData = new FormData();
      formData.append("receipt_image", file);

      try {
        const response = await fetch("/groceries/parse-receipt", {
          method: "POST",
          body: formData,
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || "Receipt parsing failed.");
        }
        populatePurchaseFormFromReceipt(form, payload);
        if (status) {
          status.textContent = "Receipt parsed. Review before adding purchase.";
          status.hidden = false;
        }
      } catch (error) {
        if (status) {
          status.textContent = error.message;
          status.hidden = false;
        }
      } finally {
        fileInput.value = "";
        updateFormEmptyState(form);
      }
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  wireDirtyForms();
  wireConfirmDeleteForms();
  wireEditSections();
  wireStagedRemoveButtons();
  wireLineItemBuilders();
  wireClearableForms();
  wireReceiptUploads();
});
