function createMeta(item) {
  const meta = document.createElement("div");
  meta.className = "field-meta";
  meta.innerHTML = `
    <span>Title: ${item.nodeTitle}</span>
    <span>Node ID: ${item.nodeId}</span>
    <span>Field: ${item.fieldPath}</span>
    <span>Type: ${item.type}</span>
  `;
  return meta;
}

function buildImageReplacement(serverOrigin, mediaUrl) {
  return new URL(mediaUrl, `${serverOrigin}/`).toString();
}

function buildDisplayUrl(mediaUrl) {
  const url = new URL(mediaUrl, `${window.location.origin}/`);
  url.searchParams.set("_ts", String(Date.now()));
  return url.toString();
}

export function TextareaField(item, value, onChange) {
  const wrapper = document.createElement("label");
  wrapper.className = "form-card";

  const title = document.createElement("span");
  title.className = "field-title";
  title.textContent = item.nodeTitle || `${item.nodeId} · ${item.fieldPath}`;

  const textarea = document.createElement("textarea");
  textarea.rows = 5;
  textarea.placeholder = "请输入文本内容";
  textarea.value = value ?? "";
  textarea.addEventListener("input", (event) => {
    onChange(event.target.value);
  });

  wrapper.append(title, createMeta(item), textarea);
  return wrapper;
}

export function ImagePickerField(item, value, onChange, options = {}) {
  let mediaItems = options.mediaItems ?? [];
  let selectedValue = value ?? "";
  const serverOrigin = options.serverOrigin ?? window.location.origin;
  const uploadDir = options.uploadDir ?? "images";
  const onOpen = options.onOpen;
  const wrapper = document.createElement("div");
  wrapper.className = "form-card";

  const title = document.createElement("span");
  title.className = "field-title";
  title.textContent = item.nodeTitle || `${item.nodeId} · ${item.fieldPath}`;

  const picker = document.createElement("button");
  picker.type = "button";
  picker.className = "image-picker";

  const preview = document.createElement("div");
  preview.className = "image-picker-preview";
  preview.textContent = selectedValue ? `已选择: ${selectedValue}` : `点击加载 ${uploadDir} 目录中的图片`;

  const thumbnail = document.createElement("img");
  thumbnail.className = "image-picker-thumb hidden";
  thumbnail.alt = `${item.nodeId} preview`;

  const gallery = document.createElement("div");
  gallery.className = "image-gallery hidden";

  const galleryTitle = document.createElement("div");
  galleryTitle.className = "image-gallery-title";
  galleryTitle.textContent = `${uploadDir} 列表`;

  const galleryList = document.createElement("div");
  galleryList.className = "image-gallery-list";

  if (selectedValue) {
    thumbnail.src = buildDisplayUrl(selectedValue);
    thumbnail.classList.remove("hidden");
  }

  function renderGalleryItems() {
    galleryList.innerHTML = "";

    if (mediaItems.length === 0) {
      const empty = document.createElement("div");
      empty.className = "image-gallery-empty";
      empty.textContent = `${uploadDir} 目录里暂时没有图片。`;
      galleryList.append(empty);
      return;
    }

    mediaItems.forEach((mediaItem) => {
      const option = document.createElement("button");
      option.type = "button";
      option.className = "image-option";

      const image = document.createElement("img");
      image.src = buildDisplayUrl(mediaItem.url);
      image.alt = mediaItem.filename;

      const label = document.createElement("span");
      label.textContent = mediaItem.filename;

      option.append(image, label);
      option.addEventListener("click", (event) => {
        event.stopPropagation();
        const replacement = buildImageReplacement(serverOrigin, mediaItem.url);
        selectedValue = replacement;
        onChange(replacement);
        preview.textContent = `已选择: ${replacement}`;
        thumbnail.src = buildDisplayUrl(mediaItem.url);
        thumbnail.classList.remove("hidden");
        gallery.classList.add("hidden");
      });

      galleryList.append(option);
    });
  }

  renderGalleryItems();

  picker.append(preview, thumbnail);
  picker.addEventListener("click", async () => {
    if (typeof onOpen === "function") {
      preview.textContent = selectedValue ? `已选择: ${selectedValue}` : `正在加载 ${uploadDir} 目录中的图片...`;
      try {
        mediaItems = (await onOpen()) ?? [];
      } finally {
        preview.textContent = selectedValue ? `已选择: ${selectedValue}` : `点击加载 ${uploadDir} 目录中的图片`;
        renderGalleryItems();
      }
    }
    gallery.classList.toggle("hidden");
  });

  gallery.append(galleryTitle, galleryList);
  wrapper.append(title, createMeta(item), picker, gallery);
  return wrapper;
}
