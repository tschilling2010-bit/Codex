// HefterPro API wrapper v4 – ES5-safe
var API = (function () {
  function request(path, opts) {
    opts = opts || {};
    var method = opts.method || "GET";
    var body = opts.body;
    var headers = opts.headers || {};
    var form = opts.form;

    var fetchOpts = { method: method, headers: {} };
    var k;
    for (k in headers) { if (headers.hasOwnProperty(k)) fetchOpts.headers[k] = headers[k]; }

    if (form) {
      fetchOpts.body = form;
    } else if (body !== undefined) {
      fetchOpts.body = JSON.stringify(body);
      fetchOpts.headers["Content-Type"] = "application/json";
    }

    return fetch(path, fetchOpts).then(function (res) {
      if (!res.ok) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          throw new Error(data.detail || data.error || res.statusText);
        });
      }
      var ct = res.headers.get("content-type") || "";
      if (ct.indexOf("application/json") !== -1) return res.json();
      return res.blob();
    });
  }

  return {
    health: function () { return request("/api/health"); },

    listProfiles: function () { return request("/api/handwriting/profile/list"); },
    getProfile: function (id) { return request("/api/handwriting/profile/" + id); },
    createProfile: function (name) {
      return request("/api/handwriting/profile/create", { method: "POST", body: { name: name } });
    },
    renameProfile: function (id, name) {
      return request("/api/handwriting/profile/" + id + "/rename", { method: "POST", body: { name: name } });
    },
    updateProfileSettings: function (id, settings) {
      return request("/api/handwriting/profile/" + id + "/settings", { method: "POST", body: settings });
    },
    deleteProfile: function (id) {
      return request("/api/handwriting/profile/" + id, { method: "DELETE" });
    },

    pairPdfUrl: function (profileId, pairIndex) {
      return "/api/handwriting/profile/" + profileId + "/pair/" + pairIndex + "/pdf";
    },
    createPair: function (profileId, pairIndex) {
      var fd = new FormData();
      if (pairIndex !== undefined && pairIndex !== null) {
        fd.append("pair_index", String(pairIndex));
      }
      return request("/api/handwriting/profile/" + profileId + "/pair/create",
        { method: "POST", form: fd });
    },
    uploadPair: function (profileId, pairIndex, page1, page2) {
      var fd = new FormData();
      fd.append("page_1", page1);
      fd.append("page_2", page2);
      return request("/api/handwriting/profile/" + profileId + "/pair/" + pairIndex + "/upload",
        { method: "POST", form: fd });
    },

    render: function (payload) {
      return request("/api/handwriting/render", { method: "POST", body: payload });
    },
    exportHandwriting: function (projectId, format) {
      var url = format === "pdf" ? "/api/handwriting/export/pdf" : "/api/handwriting/export/image";
      return request(url, { method: "POST", body: { project_id: projectId, format: format } });
    },

    hefterUpload: function (files) {
      var fd = new FormData();
      for (var i = 0; i < files.length; i++) fd.append("files", files[i]);
      return request("/api/hefter/upload", { method: "POST", form: fd });
    },
    hefterProcess: function (opts) {
      var fd = new FormData();
      fd.append("upload_id", opts.upload_id || "");
      fd.append("additional_text", opts.additional_text || "");
      fd.append("topic_hint", opts.topic_hint || "");
      return request("/api/hefter/process", { method: "POST", form: fd });
    },
    exportHefter: function (projectId, format) {
      var url = format === "pdf" ? "/api/hefter/export/pdf" : "/api/hefter/export/image";
      return request(url, { method: "POST", body: { project_id: projectId, format: format } });
    },

    listProjects: function () { return request("/api/projects/"); },
    deleteProject: function (id) { return request("/api/projects/" + id, { method: "DELETE" }); }
  };
})();
