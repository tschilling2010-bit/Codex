// HefterPro API wrapper v3
const API = (() => {
  async function request(path, { method = "GET", body, headers = {}, form } = {}) {
    const opts = { method, headers: { ...headers } };
    if (form) {
      opts.body = form;
    } else if (body !== undefined) {
      opts.body = JSON.stringify(body);
      opts.headers["Content-Type"] = "application/json";
    }
    const res = await fetch(path, opts);
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const data = await res.json();
        detail = data.detail || data.error || detail;
      } catch (_) {}
      throw new Error(detail);
    }
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json();
    return res.blob();
  }

  return {
    health: () => request("/api/health"),

    // Profile
    listProfiles: () => request("/api/handwriting/profile/list"),
    getProfile: (id) => request(`/api/handwriting/profile/${id}`),
    createProfile: (name) =>
      request("/api/handwriting/profile/create", { method: "POST", body: { name } }),
    renameProfile: (id, name) =>
      request(`/api/handwriting/profile/${id}/rename`, { method: "POST", body: { name } }),
    updateProfileSettings: (id, settings) =>
      request(`/api/handwriting/profile/${id}/settings`, { method: "POST", body: settings }),
    deleteProfile: (id) =>
      request(`/api/handwriting/profile/${id}`, { method: "DELETE" }),

    // Pairs
    createPair: (profileId, pairIndex) => {
      const fd = new FormData();
      if (pairIndex !== undefined && pairIndex !== null) {
        fd.append("pair_index", String(pairIndex));
      }
      return request(`/api/handwriting/profile/${profileId}/pair/create`,
        { method: "POST", form: fd });
    },
    uploadPair: (profileId, pairIndex, files) => {
      const fd = new FormData();
      for (const f of files) fd.append("files", f);
      return request(`/api/handwriting/profile/${profileId}/pair/${pairIndex}/upload`,
        { method: "POST", form: fd });
    },

    // Rendering
    render: (payload) => request("/api/handwriting/render", { method: "POST", body: payload }),
    exportHandwriting: (projectId, format) =>
      request(format === "pdf" ? "/api/handwriting/export/pdf" : "/api/handwriting/export/image",
        { method: "POST", body: { project_id: projectId, format } }),

    // Hefter
    hefterUpload: (files) => {
      const fd = new FormData();
      for (const f of files) fd.append("files", f);
      return request("/api/hefter/upload", { method: "POST", form: fd });
    },
    hefterProcess: ({ upload_id = "", additional_text = "", topic_hint = "" }) => {
      const fd = new FormData();
      fd.append("upload_id", upload_id);
      fd.append("additional_text", additional_text);
      fd.append("topic_hint", topic_hint);
      return request("/api/hefter/process", { method: "POST", form: fd });
    },
    exportHefter: (projectId, format) =>
      request(format === "pdf" ? "/api/hefter/export/pdf" : "/api/hefter/export/image",
        { method: "POST", body: { project_id: projectId, format } }),

    listProjects: () => request("/api/projects/"),
    deleteProject: (id) => request(`/api/projects/${id}`, { method: "DELETE" }),
  };
})();
