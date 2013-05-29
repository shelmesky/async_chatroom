// Copyright 2013 roy.lieu@gmail.com
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may
// not use this file except in compliance with the License. You may obtain
// a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
// WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
// License for the specific language governing permissions and limitations
// under the License.


window.onbeforeunload = onbeforeunload_handler;  
window.onunload = onunload_handler;  
function onbeforeunload_handler(){  
    var warning="确认退出?";          
    return warning;  
}  
   
function onunload_handler(){  
    var warning="谢谢光临";  
    alert(warning);  
}  

$(document).ready(function() {
    if (!window.console) window.console = {};
    if (!window.console.log) window.console.log = function() {};
    
    $("a[data-toggle=popover]")
      .popover()
      .click(function(e) {
        e.preventDefault()
    })

    // 为表单的submit时间添加函数
    $("body").delegate("#messageform", "submit", function() {
        newMessage($(this));
        return false;
    });
    
    // 为表单的回车键事件添加监听函数
    // POST新消息到服务端
    $("body").delegate("#messageform", "keypress", function(e) {
        if (e.keyCode == 13) {
            newMessage($(this));
            return false;
        }
    });
    
    $("#message").select();
    
    scrollY = $("#inbox").height();
    $("#msg_area").animate({scrollTop: scrollY}, 500);
    
    // 从服务端poll消息，服务端会保持长连接
    updater.poll();
});

function newMessage(form) {
    var message = form.formToDict();
    var disabled = form.find("input[type=submit]");
    disabled.disable();
    // POST新消息到服务端
    $.postJSON("/message/new", message, function(response) {
        // 服务端会返回完整的新消息，并加上message id
        // 在页面显示新消息
        updater.showMessage(response);
        if (message.id) {
            form.parent().remove();
        } else {
            form.find("input[type=text]").val("").select();
            disabled.enable();
        } });
        
        // 当server重启后
        // ajax因为错误和/poll_message尝试连接的间隔越来越长
        // 这里判断当 updater.errorSleepTime 大于 500
        // 表明/pool_message发生错误
        // 在这里执行是因为发送新消息成功，说明server已经恢复正常
        // 但是/pool_message尚未请求，所以立即请求/pool_message
        if (updater.errorSleepTime > 500)
        {
            window.setTimeout(updater.poll, 0);
        }
}

function getCookie(name) {
    var r = document.cookie.match("\\b" + name + "=([^;]*)\\b");
    return r ? r[1] : undefined;
}

jQuery.postJSON = function(url, args, callback) {
    args._xsrf = getCookie("_xsrf");
    $.ajax({url: url, data: $.param(args), dataType: "text", type: "POST",
            success: function(response) {
        if (callback) callback(eval("(" + response + ")"));
    }, error: function(response) {
        console.log("ERROR:", response)
    }});
};

jQuery.fn.formToDict = function() {
    var fields = this.serializeArray();
    var json = {}
    for (var i = 0; i < fields.length; i++) {
        json[fields[i].name] = fields[i].value;
    }
    if (json.next) delete json.next;
    return json;
};

jQuery.fn.disable = function() {
    this.enable(false);
    return this;
};

jQuery.fn.enable = function(opt_enable) {
    if (arguments.length && !opt_enable) {
        this.attr("disabled", "disabled");
    } else {
        this.removeAttr("disabled");
    }
    return this;
};

var updater = {
    errorSleepTime: 500,
    cursor: null,

    poll: function() {
        var args = {"_xsrf": getCookie("_xsrf")};
        args.room_id = $("input[name='room_id']").attr("value");
        // 设置使用长连接从服务端poll消息时的cursor
        // 即发送新消息时，从服务端返回的message id
        if (updater.cursor) args.cursor = updater.cursor;
        // 从服务端使用长连接poll消息
        // 返回消息则把消息显示到页面
        $.ajax({url: "/message/updates", type: "POST", dataType: "text",
                data: $.param(args), success: updater.onSuccess,
                error: updater.onError});
    },

    // 请求长连接ajax成功时的回调
    onSuccess: function(response) {
        try {
            updater.newMessages(eval("(" + response + ")"));
        } catch (e) {
            updater.onError();
            return;
        }
        updater.errorSleepTime = 500;
        window.setTimeout(updater.poll, 0);
    },

    onError: function(response) {
        updater.errorSleepTime *= 2;
        console.log("Poll error; sleeping for", updater.errorSleepTime, "ms");
        window.setTimeout(updater.poll, updater.errorSleepTime);
    },
    
    onLine_offLine: function(response) {
        var type = response.on_off;
        var user = response.user;
        if(type == "offline")
        {
            var user_dom = $("#" + user);
            user_dom.hide("slow", "linear");
            user_dom.remove();
        }
        else if(type == "online")
        {
            var userlist_area = $("#userlist_area");
            var content = "<div class='alert alert-error' id='" + user + "'>" + user + " " + response.remote_ip + "</div>"
            userlist_area.append(content);
            console.log(user + " online");
        }
    },

    newMessages: function(response) {
        if (!response.messages) return;
        var messages = response.messages;
        var msg_type = response.msg_type;
        // 普通消息
        if(msg_type == "normal") {
            // cursor是最新一个消息的message id
            // 设置cursor
            updater.cursor = messages[messages.length - 1].id;
            console.log(messages.length, "new normal messages, cursor:", updater.cursor);
            for (var i = 0; i < messages.length; i++) {
                updater.showMessage(messages[i]);
            }
        }
        // 用户上下线消息
        else if(msg_type == "online_offline")
        {
            updater.onLine_offLine(messages);
        }
        // 欢迎消息，不设置cursor，再请求长连接时使用上次的cursor
        // 因为这次消息的cursor不在服务端的消息缓存列表中
        // 使用此次的cursor会导致服务端认为，我们是新客户端
        // 从而发送所有缓存的消息
        else if(msg_type == "welcome_message")
        {
            console.log(messages.length, "new welcome message, cursor:", updater.cursor);
            for (var i = 0; i < messages.length; i++) {
                updater.showMessage(messages[i]);
            }
        }
    },

    showMessage: function(message) {
        if(message.status == "logout")
        {
            $("#relogin_dialog").modal("show");
            return;
        }
        // 根据message id查找重复消息
        var existing = $("#m" + message.id);
        // 如果消息已经存在则不添加
        // 这是因为在发送新消息时，服务端会把消息原封不动的返回
        // 再加上update取得的消息，就会发生消息重复
        if (existing.length > 0) return;
        var node = $(message.html);
        node.hide();
        $("#inbox").append(node);
        scrollY = $("#inbox").height();
        $("#msg_area").animate({scrollTop: scrollY}, 500);
        node.slideDown();
    }
};
