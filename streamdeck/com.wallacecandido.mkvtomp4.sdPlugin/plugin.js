var websocket = null;
var pluginUUID = null;
var timers = {};
var lastPress = {};
var API = "http://127.0.0.1:17321";

function connectElgatoStreamDeckSocket(inPort, inPluginUUID, inRegisterEvent) {
  pluginUUID = inPluginUUID;
  websocket = new WebSocket("ws://127.0.0.1:" + inPort);
  websocket.onopen = function () {
    websocket.send(JSON.stringify({ event: inRegisterEvent, uuid: pluginUUID }));
  };
  websocket.onmessage = function (evt) {
    var msg = JSON.parse(evt.data);
    var event = msg.event;
    var context = msg.context;
    var action = msg.action;
    if (event === "willAppear") {
      refresh(context, action);
      timers[context] = setInterval(function () {
        refresh(context, action);
      }, 1500);
    }
    if (event === "willDisappear") {
      if (timers[context]) {
        clearInterval(timers[context]);
        delete timers[context];
      }
    }
    if (event === "keyDown") {
      var now = Date.now();
      if (lastPress[context] && now - lastPress[context] < 400) {
        return;
      }
      lastPress[context] = now;
      var path = commandPath(action, msg.payload);
      get(path)
        .then(function (data) {
          if (data && data.ok === false) {
            send({ event: "showAlert", context: context });
          }
          apply(context, data, action);
        })
        .catch(function () {
          send({ event: "showAlert", context: context });
          send({
            event: "setTitle",
            context: context,
            payload: { title: "App off", target: 0 },
          });
        });
    }
  };
}

function commandPath(action, payload) {
  if (action && action.indexOf(".start") !== -1) return "/watch/start";
  if (action && action.indexOf(".stop") !== -1) return "/watch/stop";
  var desired = payload ? payload.userDesiredState : undefined;
  if (desired === 1 || desired === "1") return "/watch/start";
  if (desired === 0 || desired === "0") return "/watch/stop";
  return "/watch/toggle";
}

function get(path) {
  return fetch(API + path, { method: "GET", cache: "no-store" }).then(function (res) {
    return res.json();
  });
}

function refresh(context, action) {
  get("/status")
    .then(function (data) {
      apply(context, data, action);
    })
    .catch(function () {
      send({
        event: "setTitle",
        context: context,
        payload: { title: "App off", target: 0 },
      });
    });
}

function apply(context, data, action) {
  if (!data) return;
  var watching = !!data.watching;
  send({
    event: "setState",
    context: context,
    payload: { state: watching ? 1 : 0 },
  });
  var title = watching ? "Watching" : "Idle";
  if (data.ok === false) title = shortError(data.error);
  if (action && action.indexOf(".start") !== -1 && data.ok !== false) {
    title = watching ? "Watching" : "Start";
  }
  if (action && action.indexOf(".stop") !== -1 && data.ok !== false) title = "Stop";
  send({
    event: "setTitle",
    context: context,
    payload: { title: title, target: 0 },
  });
}

function shortError(err) {
  err = (err || "").toLowerCase();
  if (err.indexOf("folder") !== -1) return "No folder";
  if (err.indexOf("ffmpeg") !== -1) return "No FFmpeg";
  if (err.indexOf("write") !== -1 || err.indexOf("permission") !== -1) return "No write";
  if (err.indexOf("respond") !== -1) return "Busy";
  return "Failed";
}

function send(payload) {
  if (websocket && websocket.readyState === 1) {
    websocket.send(JSON.stringify(payload));
  }
}
