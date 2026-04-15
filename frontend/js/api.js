// Thin API wrapper for HefterPro.
const API = (() => {
  const base = "";

  async function request(path, { method = "GET", body, headers = {}, form } = {}) {
    const opts = { method, headers: { ...headers } };
    if (form) {
      opts.body = form;
    } else if (body !== undefined) {
      opts.body = JSON.stringify(body);
      opts.headers["Content-Type"] = "application/json";
    }
    const res = await fetch(base + path, opts);
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const data = await res.json();
        detail = data.detail || data.error || detail;
      } catch (_) { /* ignore */ }
      throw new Error(detail);
    }
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json();
    return res.blob();
  }

  return {
    health: () => request("/api/health"),

    // Handschrift
    listProfiles: () => request("/api/handwriting/profile/list"),
    deleteProfile: (id) => request(`/api/handwriting/profile/${id}`, { method: "DELETE" }),
    createTemplate: (name) => {
      const fd = new FormData();
      if (name) fd.append("name", name);
      return request("/api/handwriting/template/create", { method: "POST", form: fd });
    },
    uploadTemplate: (profileId, files) => {
      const fd = new FormData();
      fd.append("profile_id", profileId);
      for (const f of files) fd.append("files", f);
      return request("/api/handwriting/template/upload", { method: "POST", form: fd });
    },
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
    hefterProcess: ({ upload_id = "", additional_text = "", topic_hint = "", profile_id = "default" }) => {
      const fd = new FormData();
      fd.append("upload_id", upload_id);
      fd.append("additional_text", additional_text);
      fd.append("topic_hint", topic_hint);
      fd.append("profile_id", profile_id);
      return request("/api/hefter/process", { method: "POST", form: fd });
    },
    hefterPreview: (id) => request(`/api/hefter/preview/${id}`),
    exportHefter: (projectId, format) =>
      request(format === "pdf" ? "/api/hefter/export/pdf" : "/api/hefter/export/image",
        { method: "POST", body: { project_id: projectId, format } }),

    // Projekte
    listProjects: () => request("/api/projects/"),
    getProject: (id) => request(`/api/projects/${id}`),
    deleteProject: (id) => request(`/api/projects/${id}`, { method: "DELETE" }),

    // Einstellungen
    getSettings: () => request("/api/settings/"),
    saveSettings: (s) => request("/api/settings/", { method: "PUT", body: s }),
  };
})();
