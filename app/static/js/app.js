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
  const fieldsMarkup = `
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
  `;
  row.innerHTML = `
    <input type="hidden" name="${prefix}_id" value="">
    <input type="hidden" name="${prefix}_delete" value="false">
    ${fieldsClass ? `<div class="${fieldsClass}">${fieldsMarkup}</div>` : fieldsMarkup}
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

const restaurantState = {
  map: null,
  placesService: null,
  googleReady: false,
  restaurants: [],
  markers: new Map(),
  menuFetches: new Set(),
  selectedId: null,
};

function restaurantStatusLabel(status) {
  return (
    {
      want_to_try: "Want To Try",
      visited: "Visited",
      permanently_closed: "Permanently Closed",
    }[status] || ""
  );
}

function restaurantCategoryLabel(category) {
  return (
    {
      party_of_one: "Party of One",
      date_night: "Date Night",
      casual_dates: "Casual Dates",
      linda_only: "Linda Only",
      dessert: "Dessert",
    }[category] || ""
  );
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function restaurantMarkerColor(status) {
  return {
    want_to_try: "#2563eb",
    visited: "#286f52",
    permanently_closed: "#7c8794",
  }[status] || "#286f52";
}

function restaurantSearchText(restaurant) {
  return [
    restaurant.name,
    restaurant.google_name,
    restaurant.formatted_address,
    restaurant.cuisine,
    restaurant.tags,
    restaurant.neighborhood,
    restaurant.notes,
    restaurant.status_label,
    restaurant.category_label,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function filteredRestaurants(shell) {
  const textFilter = shell
    .querySelector("[data-restaurant-text-filter]")
    ?.value.trim()
    .toLowerCase();
  const statusFilter = shell.querySelector("[data-restaurant-status-filter]")?.value;
  const categoryFilter = shell.querySelector(
    "[data-restaurant-category-filter]",
  )?.value;
  const ratingFilter = Number(
    shell.querySelector("[data-restaurant-rating-filter]")?.value || 0,
  );

  return restaurantState.restaurants.filter((restaurant) => {
    const statusMatches = !statusFilter || restaurant.status === statusFilter;
    const categoryMatches =
      !categoryFilter || restaurant.category === categoryFilter;
    const ratingMatches =
      !ratingFilter || Number(restaurant.personal_rating || 0) >= ratingFilter;
    const textMatches =
      !textFilter || restaurantSearchText(restaurant).includes(textFilter);
    return statusMatches && categoryMatches && ratingMatches && textMatches;
  });
}

function closeRestaurantDetail() {
  closeRestaurantPhotoOverlay();
  const panel = document.querySelector("[data-restaurant-detail]");
  if (panel) {
    panel.hidden = true;
    panel.innerHTML = "";
  }
  document
    .querySelector("[data-restaurant-map]")
    ?.classList.remove("has-restaurant-detail");
  restaurantState.selectedId = null;
}

function updateRestaurantResultCount(shell, shown) {
  const count = shell.querySelector("[data-restaurant-result-count]");
  if (!count) {
    return;
  }
  const total = restaurantState.restaurants.length;
  const itemLabel = total === 1 ? "item" : "items";
  count.textContent = `${shown} of ${total} ${itemLabel} shown`;
}

function resizeRestaurantMap() {
  if (!restaurantState.map || !window.google?.maps?.event) {
    return;
  }
  window.setTimeout(() => {
    google.maps.event.trigger(restaurantState.map, "resize");
  }, 160);
}

function setRestaurantControlsCollapsed(shell, collapsed) {
  shell.classList.toggle("is-controls-collapsed", collapsed);
  const expandButton = shell.querySelector("[data-expand-restaurant-controls]");
  if (expandButton) {
    expandButton.hidden = !collapsed;
  }
  resizeRestaurantMap();
}

function showRestaurantAddSearch(shell) {
  const searchWrap = shell.querySelector("[data-restaurant-add-search]");
  const searchInput = shell.querySelector("[data-restaurant-place-search]");
  if (!searchWrap || !searchInput) {
    return;
  }
  searchWrap.hidden = false;
  window.setTimeout(() => searchInput.focus(), 0);
}

function hideRestaurantAddSearch(shell) {
  const searchWrap = shell.querySelector("[data-restaurant-add-search]");
  const searchInput = shell.querySelector("[data-restaurant-place-search]");
  if (!searchWrap) {
    return;
  }
  searchWrap.hidden = true;
  if (searchInput) {
    searchInput.value = "";
  }
}

function restaurantAddSearchIsOpen(shell) {
  const searchWrap = shell.querySelector("[data-restaurant-add-search]");
  return Boolean(searchWrap && !searchWrap.hidden);
}

function isGooglePlacesSuggestionClick(target) {
  return Boolean(target.closest?.(".pac-container"));
}

function renderRestaurantPhotos(restaurant) {
  const photos = restaurant.photos || [];
  const gallery = photos.length
    ? `<div class="restaurant-photo-grid">
        ${photos
          .map(
            (photo) => `
              <figure class="restaurant-photo">
                <button class="restaurant-photo-preview" type="button" data-restaurant-photo-preview="${escapeHtml(photo.url)}" aria-label="View larger photo">
                  <img src="${escapeHtml(photo.url)}" alt="${escapeHtml(restaurant.name)} photo" loading="lazy">
                </button>
                <button class="restaurant-photo-remove" type="button" data-confirm-delete-restaurant-photo="${photo.id}" aria-label="Remove photo">×</button>
              </figure>
            `,
          )
          .join("")}
      </div>`
    : "";

  return `
    <div class="restaurant-photo-section">
      ${gallery}
      <form class="restaurant-photo-upload" action="/restaurants/${restaurant.id}/photos" method="post" enctype="multipart/form-data" data-restaurant-photo-upload>
        <label class="restaurant-photo-upload-control">
          <span>Add photo</span>
          <input type="file" name="photo" accept="image/*">
        </label>
      </form>
    </div>
  `;
}

function renderRestaurantMenuCache(restaurant) {
  const cache = restaurant.menu_cache;
  const isFetching = restaurantState.menuFetches.has(restaurant.id);
  const fetchedAt = cache?.fetched_at
    ? new Date(cache.fetched_at).toLocaleDateString()
    : null;
  const statusText = isFetching
    ? "Fetching menu..."
    : cache
    ? [
        cache.status ? cache.status.replaceAll("_", " ") : "unknown",
        fetchedAt ? `updated ${fetchedAt}` : "",
        cache.item_count ? `${cache.item_count} items` : "",
      ]
        .filter(Boolean)
        .join(" · ")
    : "No cached menu";
  const summary = cache?.summary
    ? `<p>${escapeHtml(cache.summary)}</p>`
    : cache?.error_message
      ? `<p>${escapeHtml(cache.error_message)}</p>`
      : "";

  return `
    <section class="restaurant-menu-cache">
      <div>
        <strong>Menu cache</strong>
        <span data-restaurant-menu-status>${escapeHtml(statusText)}</span>
      </div>
      ${summary}
      <button class="ghost" type="button" data-refresh-restaurant-menu="${restaurant.id}" ${isFetching ? "disabled" : ""}>${isFetching ? "Fetching..." : "Fetch/Update Menu"}</button>
    </section>
  `;
}

function renderRestaurantMenuSearchResults(shell, results, query) {
  const container = shell.querySelector("[data-restaurant-menu-results]");
  if (!container) {
    return;
  }
  container.hidden = false;
  container.innerHTML = "";
  if (!results.length) {
    const empty = document.createElement("span");
    empty.className = "empty";
    empty.textContent = query
      ? "No cached menus match."
      : "Enter a craving to search cached menus.";
    container.append(empty);
    return;
  }

  results.forEach((result) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "restaurant-menu-result";
    button.innerHTML = `
      <strong>${escapeHtml(result.name || "Restaurant")}</strong>
      <span>${escapeHtml(result.reason || "Cached menu match.")}</span>
    `;
    button.addEventListener("click", () => {
      selectRestaurant(Number(result.restaurant_id));
    });
    container.append(button);
  });
}

async function searchRestaurantMenus(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const shell = form.closest("[data-restaurant-map]");
  const input = form.querySelector('input[name="query"]');
  const query = input?.value.trim() || "";
  const submitButton = form.querySelector('button[type="submit"]');
  if (!shell) {
    return;
  }
  if (!query) {
    renderRestaurantMenuSearchResults(shell, [], query);
    return;
  }

  if (submitButton) {
    submitButton.disabled = true;
  }
  try {
    const response = await fetch("/restaurants/menu/search", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Could not search menus.");
    }
    renderRestaurantMenuSearchResults(shell, payload.results || [], query);
  } finally {
    if (submitButton) {
      submitButton.disabled = false;
    }
  }
}

function selectRestaurant(restaurantId) {
  restaurantState.selectedId = restaurantId;
  const restaurant = restaurantState.restaurants.find(
    (item) => item.id === restaurantId,
  );
  const panel = document.querySelector("[data-restaurant-detail]");
  if (!panel || !restaurant) {
    return;
  }

  panel.hidden = false;
  panel.closest("[data-restaurant-map]")?.classList.add("has-restaurant-detail");
  panel.innerHTML = `
    <div class="restaurant-detail-heading">
      <div>
        <div class="restaurant-name-heading">
          <h2 data-restaurant-name-title>${escapeHtml(restaurant.name)}</h2>
          <input class="restaurant-name-input" name="custom_name" form="restaurant-detail-form-${restaurant.id}" value="${escapeHtml(restaurant.custom_name)}" placeholder="${escapeHtml(restaurant.google_name || restaurant.name)}" aria-label="Custom restaurant name" data-restaurant-name-input hidden>
          <button class="restaurant-name-edit-button" type="button" title="Edit custom name" aria-label="Edit custom name" data-edit-restaurant-name>
            <span aria-hidden="true">✎</span>
          </button>
        </div>
        ${
          restaurant.formatted_address
            ? `<small>${escapeHtml(restaurant.formatted_address)}</small>`
            : ""
        }
      </div>
      <button class="ghost" type="button" data-close-restaurant-detail>Close</button>
    </div>
    <form id="restaurant-detail-form-${restaurant.id}" class="restaurant-detail-form" action="/restaurants/${restaurant.id}" method="post">
      <div class="restaurant-detail-links">
        ${
          restaurant.google_maps_uri
            ? `<a href="${escapeHtml(restaurant.google_maps_uri)}" target="_blank" rel="noreferrer">Google Maps</a>`
            : ""
        }
        ${
          restaurant.website_uri
            ? `<a href="${escapeHtml(restaurant.website_uri)}" target="_blank" rel="noreferrer">Website</a>`
            : ""
        }
        ${
          restaurant.phone_number
            ? `<span>${escapeHtml(restaurant.phone_number)}</span>`
            : ""
        }
      </div>
      <div class="form-row">
        <label>
          Status
          <select name="status">
            ${["want_to_try", "visited", "permanently_closed"]
              .map(
                (status) =>
                  `<option value="${status}" ${
                    restaurant.status === status ? "selected" : ""
                  }>${restaurantStatusLabel(status)}</option>`,
              )
              .join("")}
          </select>
        </label>
        <label>
          Category
          <select name="category">
            <option value="">Uncategorized</option>
            ${["party_of_one", "date_night", "casual_dates", "linda_only", "dessert"]
              .map(
                (category) =>
                  `<option value="${category}" ${
                    restaurant.category === category ? "selected" : ""
                  }>${restaurantCategoryLabel(category)}</option>`,
              )
              .join("")}
          </select>
        </label>
      </div>
      <div class="form-row">
        <label>
          Rating
          <select name="personal_rating">
            <option value="">Unrated</option>
            ${[1, 2, 3, 4, 5]
              .map(
                (rating) =>
                  `<option value="${rating}" ${
                    restaurant.personal_rating === rating ? "selected" : ""
                  }>${rating}</option>`,
              )
              .join("")}
          </select>
        </label>
        <label>
          Cuisine
          <input name="cuisine" value="${escapeHtml(restaurant.cuisine)}" placeholder="Thai, pizza, sushi">
        </label>
        <label>
          Neighborhood
          <input name="neighborhood" value="${escapeHtml(restaurant.neighborhood)}" placeholder="Mission, Oakland, nearby">
        </label>
      </div>
      <div class="form-row">
        <label>
          Tags
          <input name="tags" value="${escapeHtml(restaurant.tags)}" placeholder="date night, patio, kid-friendly">
        </label>
        <label>
          Price
          <input name="price_level" value="${escapeHtml(restaurant.price_level)}" placeholder="$, $$, $$$">
        </label>
      </div>
      <label>
        Notes
        <textarea name="notes" rows="5" placeholder="What to order, who recommended it, visit notes">${escapeHtml(restaurant.notes)}</textarea>
      </label>
    </form>
    ${renderRestaurantMenuCache(restaurant)}
    ${renderRestaurantPhotos(restaurant)}
    <div class="restaurant-detail-actions">
      <button form="restaurant-detail-form-${restaurant.id}" type="submit">Save</button>
      <form class="restaurant-delete-form js-confirm-delete" action="/restaurants/${restaurant.id}/delete" method="post">
      <button class="ghost" type="submit">Delete</button>
      </form>
    </div>
  `;

  panel
    .querySelector("[data-close-restaurant-detail]")
    ?.addEventListener("click", closeRestaurantDetail);
  panel
    .querySelector("[data-edit-restaurant-name]")
    ?.addEventListener("click", () => {
      const title = panel.querySelector("[data-restaurant-name-title]");
      const input = panel.querySelector("[data-restaurant-name-input]");
      if (!title || !input) {
        return;
      }
      title.hidden = true;
      input.hidden = false;
      input.focus();
      input.select();
    });
  panel
    .querySelector(".restaurant-detail-form")
    ?.addEventListener("submit", saveRestaurantDetailForm);
  panel
    .querySelector("[data-restaurant-photo-upload] input")
    ?.addEventListener("change", uploadRestaurantPhoto);
  panel
    .querySelector("[data-refresh-restaurant-menu]")
    ?.addEventListener("click", refreshRestaurantMenu);
  panel.addEventListener("click", handleRestaurantPhotoPreviewClick);
  panel.addEventListener("click", handleRestaurantPhotoDeleteClick);
  wireConfirmDeleteForms();
  panel
    .querySelector(".restaurant-delete-form")
    ?.addEventListener("submit", deleteRestaurantDetailForm);
}

async function refreshRestaurantMenu(event) {
  const button = event.currentTarget;
  const restaurantId = Number(button.dataset.refreshRestaurantMenu);
  if (!restaurantId) {
    return;
  }
  restaurantState.menuFetches.add(restaurantId);
  button.disabled = true;
  button.textContent = "Fetching...";
  try {
    const response = await fetch(`/restaurants/${restaurantId}/menu/refresh`, {
      method: "POST",
      headers: { Accept: "application/json" },
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Could not fetch menu.");
    }
    updateRestaurantFromPayload(payload.restaurant);
    selectRestaurant(payload.restaurant.id);
  } finally {
    restaurantState.menuFetches.delete(restaurantId);
    if (restaurantState.selectedId === restaurantId) {
      selectRestaurant(restaurantId);
    }
  }
}

function handleRestaurantPhotoPreviewClick(event) {
  const button = event.target.closest("[data-restaurant-photo-preview]");
  if (!button) {
    return;
  }
  showRestaurantPhotoOverlay(button);
}

function showRestaurantPhotoOverlay(button) {
  const url = button.dataset.restaurantPhotoPreview;
  if (!url) {
    return;
  }

  closeRestaurantPhotoOverlay();
  const overlay = document.createElement("div");
  overlay.className = "restaurant-photo-overlay";
  overlay.dataset.restaurantPhotoOverlay = "";
  overlay.innerHTML = `
    <div class="restaurant-photo-overlay-frame">
      <button class="restaurant-photo-overlay-close" type="button" aria-label="Close photo">×</button>
      <img src="${escapeHtml(url)}" alt="">
    </div>
  `;
  overlay.addEventListener("click", (overlayEvent) => {
    if (
      overlayEvent.target === overlay ||
      overlayEvent.target.closest(".restaurant-photo-overlay-close")
    ) {
      overlay.remove();
    }
  });
  document.body.append(overlay);
}

function closeRestaurantPhotoOverlay() {
  document.querySelector("[data-restaurant-photo-overlay]")?.remove();
}

function handleRestaurantPhotoDeleteClick(event) {
  const confirmButton = event.target.closest("[data-delete-restaurant-photo]");
  if (confirmButton) {
    deleteRestaurantPhoto(confirmButton);
    return;
  }

  const cancelButton = event.target.closest("[data-cancel-delete-restaurant-photo]");
  if (cancelButton) {
    cancelButton.closest(".restaurant-photo-delete-confirm")?.remove();
    return;
  }

  const removeButton = event.target.closest("[data-confirm-delete-restaurant-photo]");
  if (!removeButton) {
    return;
  }

  const photo = removeButton.closest(".restaurant-photo");
  if (!photo) {
    return;
  }

  photo.querySelector(".restaurant-photo-delete-confirm")?.remove();
  const confirmation = document.createElement("div");
  confirmation.className = "restaurant-photo-delete-confirm";
  confirmation.innerHTML = `
    <span>Are you sure?</span>
    <div>
      <button type="button" data-delete-restaurant-photo="${removeButton.dataset.confirmDeleteRestaurantPhoto}">Delete</button>
      <button type="button" class="ghost" data-cancel-delete-restaurant-photo>Cancel</button>
    </div>
  `;
  photo.append(confirmation);
}

async function uploadRestaurantPhoto(event) {
  const input = event.currentTarget;
  const form = input.closest("form");
  if (!form || !input.files.length) {
    return;
  }

  const formData = new FormData(form);
  input.disabled = true;
  try {
    const response = await fetch(form.action, {
      method: "POST",
      headers: { Accept: "application/json" },
      body: formData,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Could not upload photo.");
    }
    updateRestaurantFromPayload(payload.restaurant);
    selectRestaurant(payload.restaurant.id);
  } finally {
    form.reset();
    input.disabled = false;
  }
}

async function deleteRestaurantPhoto(button) {
  const photoId = button.dataset.deleteRestaurantPhoto;
  const restaurantId = restaurantState.selectedId;
  if (!photoId || !restaurantId) {
    return;
  }

  button.disabled = true;
  try {
    const response = await fetch(
      `/restaurants/${restaurantId}/photos/${photoId}/delete`,
      {
        method: "POST",
        headers: { Accept: "application/json" },
      },
    );
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Could not delete photo.");
    }
    if (payload.restaurant) {
      updateRestaurantFromPayload(payload.restaurant);
      selectRestaurant(payload.restaurant.id);
    }
  } finally {
    button.disabled = false;
  }
}

function updateRestaurantFromPayload(payload) {
  const index = restaurantState.restaurants.findIndex(
    (restaurant) => restaurant.id === payload.id,
  );
  if (index >= 0) {
    restaurantState.restaurants[index] = payload;
  }
}

async function saveRestaurantDetailForm(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = form.querySelector('button[type="submit"]');
  if (submitButton) {
    submitButton.disabled = true;
  }

  try {
    const response = await fetch(form.action, {
      method: "POST",
      headers: { Accept: "application/json" },
      body: new FormData(form),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Could not save restaurant.");
    }

    updateRestaurantFromPayload(payload);
    renderRestaurants({ fitMap: false });
    closeRestaurantDetail();
  } finally {
    if (submitButton) {
      submitButton.disabled = false;
    }
  }
}

async function deleteRestaurantDetailForm(event) {
  if (event.defaultPrevented) {
    return;
  }
  event.preventDefault();
  const form = event.currentTarget;
  const response = await fetch(form.action, {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Could not delete restaurant.");
  }

  restaurantState.restaurants = restaurantState.restaurants.filter(
    (restaurant) => restaurant.id !== payload.deleted,
  );
  renderRestaurants({ fitMap: false });
  closeRestaurantDetail();
}

function renderRestaurantList(shell, restaurants) {
  const list = shell.querySelector("[data-restaurant-list]");
  if (!list) {
    return;
  }

  list.innerHTML = "";
  if (!restaurants.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "No restaurants match the current filters.";
    list.append(empty);
    return;
  }

  restaurants.forEach((restaurant) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "restaurant-list-item";
    button.dataset.restaurantId = restaurant.id;
    button.innerHTML = `
      <span>
        <strong>${escapeHtml(restaurant.name)}</strong>
        ${
          restaurant.neighborhood || restaurant.formatted_address
            ? `<small>${escapeHtml(restaurant.neighborhood || restaurant.formatted_address)}</small>`
            : ""
        }
      </span>
      <span class="restaurant-list-pills">
        <span class="pill">${escapeHtml(restaurant.status_label)}</span>
        ${
          restaurant.category_label
            ? `<span class="pill">${escapeHtml(restaurant.category_label)}</span>`
            : ""
        }
      </span>
    `;
    button.addEventListener("click", () => {
      selectRestaurant(restaurant.id);
      const marker = restaurantState.markers.get(restaurant.id);
      if (restaurantState.map) {
        restaurantState.map.panTo({
          lat: restaurant.latitude,
          lng: restaurant.longitude,
        });
        restaurantState.map.setZoom(Math.max(restaurantState.map.getZoom() || 12, 14));
      }
      marker?.element?.classList.add("restaurant-marker-selected");
    });
    list.append(button);
  });
}

function renderRestaurantMarkers(shell, restaurants, options = {}) {
  if (!restaurantState.map || !window.google?.maps?.marker) {
    return;
  }

  restaurantState.markers.forEach((marker) => {
    marker.map = null;
  });
  restaurantState.markers.clear();

  const bounds = new google.maps.LatLngBounds();
  restaurants.forEach((restaurant) => {
    const markerElement = document.createElement("button");
    markerElement.type = "button";
    markerElement.className = "restaurant-marker";
    markerElement.style.setProperty(
      "--restaurant-marker-color",
      restaurantMarkerColor(restaurant.status),
    );
    markerElement.setAttribute("aria-label", restaurant.name);
    markerElement.append(document.createTextNode(restaurant.name.charAt(0).toUpperCase()));

    const tooltip = document.createElement("span");
    tooltip.className = "restaurant-marker-tooltip";
    tooltip.textContent = restaurant.name;
    markerElement.append(tooltip);

    const marker = new google.maps.marker.AdvancedMarkerElement({
      map: restaurantState.map,
      position: { lat: restaurant.latitude, lng: restaurant.longitude },
      content: markerElement,
    });
    marker.addListener("click", () => selectRestaurant(restaurant.id));
    restaurantState.markers.set(restaurant.id, marker);
    bounds.extend({ lat: restaurant.latitude, lng: restaurant.longitude });
  });

  if (options.fitMap === false) {
    return;
  }
  if (restaurants.length > 1) {
    restaurantState.map.fitBounds(bounds, 56);
  } else if (restaurants.length === 1) {
    restaurantState.map.setCenter(bounds.getCenter());
    restaurantState.map.setZoom(14);
  }
}

function renderRestaurants(options = {}) {
  const shell = document.querySelector("[data-restaurant-map]");
  if (!shell) {
    return;
  }
  const restaurants = filteredRestaurants(shell);
  updateRestaurantResultCount(shell, restaurants.length);
  renderRestaurantList(shell, restaurants);
  renderRestaurantMarkers(shell, restaurants, options);
}

function priceLevelLabel(priceLevel) {
  const value = Number(priceLevel);
  if (!Number.isFinite(value) || value <= 0) {
    return "";
  }
  return "$".repeat(Math.min(value, 4));
}

async function saveGoogleRestaurant(place) {
  const location = place.geometry?.location;
  const response = await fetch("/restaurants/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      google_place_id: place.place_id,
      name: place.name,
      formatted_address: place.formatted_address,
      latitude: location.lat(),
      longitude: location.lng(),
      google_maps_uri: place.url,
      website_uri: place.website,
      phone_number: place.international_phone_number || place.formatted_phone_number,
      price_level: priceLevelLabel(place.price_level),
    }),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Could not save restaurant.");
  }
  return payload;
}

async function showSavedGoogleRestaurant(shell, place) {
  const restaurant = await saveGoogleRestaurant(place);
  await loadRestaurants();
  hideRestaurantAddSearch(shell);
  selectRestaurant(restaurant.id);
  if (restaurantState.map) {
    restaurantState.map.panTo({
      lat: restaurant.latitude,
      lng: restaurant.longitude,
    });
    restaurantState.map.setZoom(14);
  }
}

function wireRestaurantAutocomplete(shell) {
  const input = shell.querySelector("[data-restaurant-place-search]");
  if (!input || !window.google?.maps?.places) {
    return;
  }

  const autocomplete = new google.maps.places.Autocomplete(input, {
    fields: [
      "formatted_address",
      "formatted_phone_number",
      "geometry",
      "international_phone_number",
      "name",
      "place_id",
      "price_level",
      "url",
      "website",
    ],
    strictBounds: false,
    types: ["restaurant"],
  });
  if (restaurantState.map) {
    autocomplete.bindTo("bounds", restaurantState.map);
  }

  autocomplete.addListener("place_changed", async () => {
    const place = autocomplete.getPlace();
    if (!place.place_id || !place.geometry?.location) {
      return;
    }
    input.disabled = true;
    try {
      await showSavedGoogleRestaurant(shell, place);
    } finally {
      input.disabled = false;
    }
  });
}

function getGooglePlaceDetails(placeId) {
  return new Promise((resolve, reject) => {
    if (!restaurantState.placesService) {
      reject(new Error("Google Places is not ready."));
      return;
    }
    restaurantState.placesService.getDetails(
      {
        placeId,
        fields: [
          "formatted_address",
          "formatted_phone_number",
          "geometry",
          "international_phone_number",
          "name",
          "place_id",
          "price_level",
          "url",
          "website",
        ],
      },
      (place, status) => {
        if (status === google.maps.places.PlacesServiceStatus.OK && place) {
          resolve(place);
          return;
        }
        reject(new Error(`Could not load place details: ${status}`));
      },
    );
  });
}

async function saveRestaurantFromMapClick(shell, event) {
  if (!event.placeId) {
    closeRestaurantDetail();
    return;
  }
  event.stop();
  try {
    const place = await getGooglePlaceDetails(event.placeId);
    if (!place.place_id || !place.geometry?.location) {
      return;
    }
    await showSavedGoogleRestaurant(shell, place);
  } catch (error) {
    console.error(error);
  }
}

async function loadRestaurants() {
  const response = await fetch("/restaurants/data");
  const payload = await response.json();
  restaurantState.restaurants = payload.restaurants || [];
  renderRestaurants();
}

function initRestaurantMapWhenReady() {
  const shell = document.querySelector("[data-restaurant-map]");
  if (!shell || shell.dataset.hasGoogleConfig !== "true" || !restaurantState.googleReady) {
    return;
  }
  const canvas = shell.querySelector("[data-restaurant-map-canvas]");
  if (!canvas || restaurantState.map) {
    return;
  }

  restaurantState.map = new google.maps.Map(canvas, {
    center: { lat: 37.7749, lng: -122.4194 },
    zoom: 11,
    mapId: shell.dataset.mapId,
    tilt: 0,
    heading: 0,
    gestureHandling: "greedy",
    mapTypeControl: false,
    streetViewControl: false,
    fullscreenControl: true,
  });

  restaurantState.placesService = new google.maps.places.PlacesService(
    restaurantState.map,
  );
  restaurantState.map.addListener("click", (event) => {
    saveRestaurantFromMapClick(shell, event);
  });
  wireRestaurantAutocomplete(shell);
  renderRestaurants();
}

function wireRestaurantMap() {
  const shell = document.querySelector("[data-restaurant-map]");
  if (!shell) {
    return;
  }

  shell.querySelectorAll("[data-restaurant-text-filter], [data-restaurant-status-filter], [data-restaurant-category-filter], [data-restaurant-rating-filter]").forEach((element) => {
    element.addEventListener("input", renderRestaurants);
    element.addEventListener("change", renderRestaurants);
  });
  shell
    .querySelector("[data-show-restaurant-add]")
    ?.addEventListener("click", (event) => {
      event.stopPropagation();
      showRestaurantAddSearch(shell);
    });
  shell
    .querySelector("[data-restaurant-menu-search]")
    ?.addEventListener("submit", searchRestaurantMenus);
  shell
    .querySelector("[data-collapse-restaurant-controls]")
    ?.addEventListener("click", () => setRestaurantControlsCollapsed(shell, true));
  shell
    .querySelector("[data-expand-restaurant-controls]")
    ?.addEventListener("click", () => setRestaurantControlsCollapsed(shell, false));
  const dismissRestaurantAddSearch = (event) => {
    const searchWrap = shell.querySelector("[data-restaurant-add-search]");
    if (
      !restaurantAddSearchIsOpen(shell) ||
      searchWrap?.contains(event.target) ||
      event.target.closest?.("[data-show-restaurant-add]") ||
      isGooglePlacesSuggestionClick(event.target)
    ) {
      return;
    }
    hideRestaurantAddSearch(shell);
  };
  document.addEventListener("pointerdown", dismissRestaurantAddSearch, true);
  document.addEventListener("click", dismissRestaurantAddSearch, true);

  loadRestaurants();
  initRestaurantMapWhenReady();
}

window.initRestaurantGoogle = () => {
  window.restaurantGoogleReady = true;
  restaurantState.googleReady = true;
  initRestaurantMapWhenReady();
};

document.addEventListener("restaurant-google-ready", () => {
  restaurantState.googleReady = true;
  initRestaurantMapWhenReady();
});

document.addEventListener("DOMContentLoaded", () => {
  if (window.restaurantGoogleReady) {
    restaurantState.googleReady = true;
  }
  wireDirtyForms();
  wireConfirmDeleteForms();
  wireEditSections();
  wireStagedRemoveButtons();
  wireLineItemBuilders();
  wireClearableForms();
  wireReceiptUploads();
  wireRestaurantMap();
});
