// HefterPro API wrapper v2
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

    listProfiles: () => request("/api/handwriting/profile/list"),
    deleteProfile: (id) => request(`/api/handwriting/profile/${id}`, { method: "DELETE" }),
    render: (payload) => request("/api/handwriting/render", { method: "POST", body: payload }),
    exportHandwriting: (projectId, format) =>
      request(format === "pdf" ? "/api/handwriting/export/pdf" : "/api/handwriting/export/image",
        { method: "POST", body: { project_id: projectId, format } }),

    createTemplate: (name) => {
      const fd = new FormData();
      if (name) fd.append("name", name);
      return request("/api/handwriting/template/create", { method: "POST", form: fd });
    },
    uploadTemplate: (profileId, name, files) => {
      const fd = new FormData();
      fd.append("profile_id", profileId);
      fd.append("name", name);
      for (const f of files) fd.append("files", f);
      return request("/api/handwriting/template/upload", { method: "POST", form: fd });
    },

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
