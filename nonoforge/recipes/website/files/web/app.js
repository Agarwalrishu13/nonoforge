/* The only moving part of your website: it asks the little program for the
   pictures in the photos folder and lays them out. If there are none, the
   photo section stays hidden so the page still looks finished. */

const gallery = document.getElementById("gallery");
const section = document.getElementById("photos");

fetch("/api/photos")
  .then((response) => response.json())
  .then((data) => {
    const photos = data.photos || [];
    if (!photos.length) return; // no photos yet: leave the section hidden
    section.hidden = false;
    photos.forEach((name) => {
      const image = document.createElement("img");
      image.src = "/photo/" + encodeURIComponent(name);
      image.alt = name.replace(/\.[a-z0-9]+$/i, "").replace(/[-_]+/g, " ");
      image.loading = "lazy";
      gallery.appendChild(image);
    });
  })
  .catch(() => {
    /* If the little program is not running the gallery simply does not appear. */
  });
