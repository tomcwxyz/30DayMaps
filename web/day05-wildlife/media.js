/* Day 05: media licence filtering for editorial field-guide photographs.
 *
 * A photograph is an illustration of a species, NOT evidence it was recorded
 * at the visitor's location. Never fall back to unlicensed images, assume
 * the occurrence licence applies to separate media, or fabricate a photo.
 *
 * Pure functions run in Node unit tests and browser; image fetches use
 * original provider URLs and carry a direct link to the GBIF occurrence.
 */
(function(root) {
  "use strict";
  const OPEN_LICENSES = [
    {id:"CC0", re:/^(?:CC0(?:[_ -]?1[._]?0)?|https?:\/\/creativecommons\.org\/publicdomain\/zero\/1\.0\/?)$/i},
    {id:"CC BY 4.0", re:/^(?:CC[_ -]?BY[_ -]?4[._]?0|https?:\/\/creativecommons\.org\/licenses\/by\/4\.0\/?)$/i},
    {id:"CC BY 3.0", re:/^(?:CC[_ -]?BY[_ -]?3[._]?0|https?:\/\/creativecommons\.org\/licenses\/by\/3\.0\/?)$/i}
  ];
  function mediaLicence(value) {
    if(typeof value !== "string") return null;
    const normalized=value.trim().replace(/\/(?:legalcode|deed\.en)\/?$/i,"");
    const found=OPEN_LICENSES.find(licence=>licence.re.test(normalized));
    return found ? found.id : null;
  }
  function safeImageUrl(value) {
    if(typeof value !== "string" || value.length > 2048) return null;
    try {
      const url=new URL(value);
      return url.protocol==="https:" && !url.username && !url.password ? url.href : null;
    } catch (_) { return null; }
  }
  function usableMedia(occurrence, targetSpeciesKey) {
    if(!occurrence || String(occurrence.speciesKey)!==String(targetSpeciesKey)) return null;
    for (const medium of (Array.isArray(occurrence.media) ? occurrence.media : [])) {
      const allowed=mediaLicence(medium.license);
      const url=safeImageUrl(medium.identifier);
      const type=String(medium.type || "").toLowerCase();
      const format=String(medium.format || "").toLowerCase();
      if(!allowed || !url ||
        !(type==="stillimage" || type==="image" || format.startsWith("image/")) ||
        format==="image/svg+xml") continue;
      return {
        url, licence:allowed,
        creator:String(medium.creator || medium.rightsHolder || "Photographer not supplied").slice(0,120),
        sourceUrl:"https://www.gbif.org/occurrence/"+encodeURIComponent(String(occurrence.key)),
        label:"Photograph of this species (not necessarily recorded nearby)"
      };
    }
    return null;
  }
  function pickSpeciesPhoto(results, key) {
    for(const item of (Array.isArray(results) ? results : [])) {
      const found=usableMedia(item,key);
      if(found) return found;
    }
    return null;
  }
  const api={mediaLicence,safeImageUrl,usableMedia,pickSpeciesPhoto};
  if(typeof module!=="undefined" && module.exports) module.exports=api;
  root.SightMedia=api;
})(typeof globalThis!=="undefined" ? globalThis : this);
