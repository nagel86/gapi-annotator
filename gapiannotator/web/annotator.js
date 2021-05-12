/**
 Copyright (C) 2021, Sebastian Nagel.

 This file is part of the module 'gapiannotator' and is released under
 the MIT License: https://opensource.org/licenses/MIT
**/

$( document ).ready(function() {
    GUI.init();
});

class GUI {
    static init() {
        // init some Helper functions
        Helper.some_hacks();
        //Helper.disableContextMenu();

        // connect WebSocket
        RemoteClient.ws_connect();

        // init loading overlay;
        GUI.loading = new Overlay('Loading, please wait...',false,'loading-overlay');

        // load page on history change
        window.onpopstate = () => GUI.load_page(GUI.path,false);

        // load page once settings are loaded
        Settings.load(() => GUI.load_page(GUI.path,false));
    }
    
    static get path() {
        return window.location.pathname.match(/^\/([^/]*)$/i)[1].toLowerCase() || 'facetagger';
    }

    static load_page(path,pushstate=true) {
        path = path.toLowerCase();
        if (Settings.changed) {
            new Dialog("dialog-unsaved-settings","Unsaved settings",'There are unsaved settings, do you want to save them before?', function() {
                Settings.save(()=>GUI.load_page(path))
                return true;
            }, function() {
                Settings.discard_changes();
                GUI.load_page(path);
                return true;
            },false);
            return;
        }

        if (pushstate)
            history.pushState(null, path.capitalize(), path);
        // remove all current listeners/callbacks
        RemoteClient.remove_callbacks();
        $('body *').off().remove();

        GUI.page = new Page[path.capitalize()]();
        document.title = path.capitalize();
    }
}

class Popup {
    static timeout = 5000;
    static active_popups = [];
    static max_popups = 3;
    static container = $('<div>',{id:'popup-container'});

    constructor (title,message) {
        this.elem = $('<div>',{"class":"popup"})
                    .append($('<div>',{"class":"popup-header"}).append(title))
                    .append($('<div>',{"class":"popup-content"}).append(message));
        this.show(Popup.timeout);
    }

    show(timeout = Popup.timeout) {
        Popup._add_popup(this);
        var popup = this;
        this.timer = setTimeout(function(){
            popup.delete();
        },timeout);
    }

    delete() {
        clearTimeout(this.timer);
        Popup._remove_popup(this);
    }

    static _add_popup(popup) {
        if (Popup.active_popups.length == 0)
            Popup.container.appendTo('body');

        while (Popup.active_popups.length >= Popup.max_popups)
            Popup.active_popups[0].delete(); //remove oldest popups

        Popup.active_popups.push(popup);
        Popup.container.append(popup.elem);
    }

    static _remove_popup(popup) {
        const index = Popup.active_popups.indexOf(popup);
        if (index > -1)
            Popup.active_popups.splice(index, 1);
        popup.elem.remove();

        if (Popup.active_popups.length == 0)
            Popup.container.detach();
    }
}

class Dialog {
    constructor(id="dialog",title="",content="",ok=function(){return true;},cancel=function(){return true;},ignorable=false) {
        this.id = id;
        this.ignorable = ignorable;
        this.elem = $('<div>',{id: id, "class":"dialog"})
                    .append($('<div>',{"class":"dialog-title"}))
                    .append($('<div>',{"class":"dialog-content"}))
                    .append($('<div>',{"class":"dialog-askagain"})
                            .append($('<input>',{type:"checkbox",id:id+'-checkbox'}).prop("checked",!this.askagain))
                            .append($('<label>',{for:id+'-checkbox'}).append("Don't ask again")))
                    .append($('<div>',{"class":"dialog-buttons"}));
        this.overlay = new Overlay(this.elem,false);
        this.title = title;
        this.content = content;
        this.btn_ok = $('<input>',{type: "button",value:"Ok"});
        this.on_ok = ok;
        this.btn_cancel = $('<input>',{type: "button",value:"Cancel"});
        this.on_cancel = cancel;
        this.show();
    }

    get askagain() {
        return Cookies.get(this.id+'-askagain') != 'false';
    }

    set askagain(value) {
        return Cookies.set(this.id+'-askagain',value);
    }

    set title(title) {
        this.elem.find('.dialog-title').empty().append(title);
    }

    set content(content) {
        this.elem.find('.dialog-content').empty().append(content);
    }

    set on_ok(fun) {
        var dialog = this;
        this._on_ok_fun = fun;
        if (fun == null) {
            this.btn_ok.detach();
            this.elem.find('.dialog-askagain').hide()
        } else {
            this.elem.find('.dialog-askagain').toggle(this.ignorable);
            this.btn_ok
                       .on('click',function(){
                            if (fun()) dialog.hide();
                            dialog.askagain = !dialog.elem.find('.dialog-askagain input[type="checkbox"]').prop('checked');
                        })
                       .prependTo(this.elem.find('.dialog-buttons'));
        }
    }

    set on_cancel(fun) {
        var dialog = this;
        if (fun == null) {
            this.btn_cancel.detach();
        } else {
            this.btn_cancel.off('click')
                           .on('click',function(){if (fun()) dialog.hide()})
                           .appendTo(this.elem.find('.dialog-buttons'));
        }
    }

    show() {
        if (!this.askagain && this.ignorable) {
            if (this._on_ok_fun != null)
                this._on_ok_fun()
        } else {
            this.overlay.show();
            this.btn_ok.focus();
        }
    }

    hide() {
        this.overlay.hide();
    }

    delete() {
        this.overlay.delete();
    }
}

class Overlay {
    static visible = [];

    constructor(content='',close_on_click=false,overlay_class='',onkeydown=function(evt){}) {
        var overlay = this;

        overlay.elem = $('<div>',{"class":overlay_class+" overlay"});
        overlay.isclosable = close_on_click;
        overlay.keydown = function(evt) {
            var key = (evt.which || evt.keyCode);
            if(key == 27 && overlay.isclosable) {//esc
                overlay.hide();
                evt.preventDefault();
            }
            onkeydown(evt);
        }
        if (close_on_click) {
            overlay.elem.on('click',() => overlay.hide());
        }
        overlay.content = content;
    }

    static get any_visible() {
        return Overlay.visible.length > 0;
    }

    set content(content) {
        this.elem.empty();
        this.elem.append(content);
    }

    show() {
        if (Overlay.visible.indexOf(this) == -1) {
            this.elem.appendTo('body');
            Overlay.visible.push(this);
            $(document).on('keydown',this.keydown);
            this.elem.trigger('visible');
        }
    }

    hide() {
        const index = Overlay.visible.indexOf(this);
        if (index > -1) {
            Overlay.visible.splice(index, 1);
            $(document).off('keydown',this.keydown);
            this.elem.detach();
            this.elem.trigger('hidden');
        }
    }

    delete() {
        const index = Overlay.visible.indexOf(this);
        if (index > -1) {
            Overlay.visible.splice(index, 1);
            $(document).off('keydown',this.keydown);
            this.elem.remove();
            this.elem.trigger('hidden');
        }
    }
}

class Settings {
    static SUPPORTED_LANGUAGES = [{'language': 'af', 'name': 'Afrikaans'}, {'language': 'sq', 'name': 'Albanian'}, {'language': 'am', 'name': 'Amharic'}, {'language': 'ar', 'name': 'Arabic'}, {'language': 'hy', 'name': 'Armenian'}, {'language': 'az', 'name': 'Azerbaijani'}, {'language': 'eu', 'name': 'Basque'}, {'language': 'be', 'name': 'Belarusian'}, {'language': 'bn', 'name': 'Bengali'}, {'language': 'bs', 'name': 'Bosnian'}, {'language': 'bg', 'name': 'Bulgarian'}, {'language': 'ca', 'name': 'Catalan'}, {'language': 'ceb', 'name': 'Cebuano'}, {'language': 'ny', 'name': 'Chichewa'}, {'language': 'zh-CN', 'name': 'Chinese (Simplified)'}, {'language': 'zh-TW', 'name': 'Chinese (Traditional)'}, {'language': 'co', 'name': 'Corsican'}, {'language': 'hr', 'name': 'Croatian'}, {'language': 'cs', 'name': 'Czech'}, {'language': 'da', 'name': 'Danish'}, {'language': 'nl', 'name': 'Dutch'}, {'language': 'en', 'name': 'English'}, {'language': 'eo', 'name': 'Esperanto'}, {'language': 'et', 'name': 'Estonian'}, {'language': 'tl', 'name': 'Filipino'}, {'language': 'fi', 'name': 'Finnish'}, {'language': 'fr', 'name': 'French'}, {'language': 'fy', 'name': 'Frisian'}, {'language': 'gl', 'name': 'Galician'}, {'language': 'ka', 'name': 'Georgian'}, {'language': 'de', 'name': 'German'}, {'language': 'el', 'name': 'Greek'}, {'language': 'gu', 'name': 'Gujarati'}, {'language': 'ht', 'name': 'Haitian Creole'}, {'language': 'ha', 'name': 'Hausa'}, {'language': 'haw', 'name': 'Hawaiian'}, {'language': 'iw', 'name': 'Hebrew'}, {'language': 'hi', 'name': 'Hindi'}, {'language': 'hmn', 'name': 'Hmong'}, {'language': 'hu', 'name': 'Hungarian'}, {'language': 'is', 'name': 'Icelandic'}, {'language': 'ig', 'name': 'Igbo'}, {'language': 'id', 'name': 'Indonesian'}, {'language': 'ga', 'name': 'Irish'}, {'language': 'it', 'name': 'Italian'}, {'language': 'ja', 'name': 'Japanese'}, {'language': 'jw', 'name': 'Javanese'}, {'language': 'kn', 'name': 'Kannada'}, {'language': 'kk', 'name': 'Kazakh'}, {'language': 'km', 'name': 'Khmer'}, {'language': 'rw', 'name': 'Kinyarwanda'}, {'language': 'ko', 'name': 'Korean'}, {'language': 'ku', 'name': 'Kurdish (Kurmanji)'}, {'language': 'ky', 'name': 'Kyrgyz'}, {'language': 'lo', 'name': 'Lao'}, {'language': 'la', 'name': 'Latin'}, {'language': 'lv', 'name': 'Latvian'}, {'language': 'lt', 'name': 'Lithuanian'}, {'language': 'lb', 'name': 'Luxembourgish'}, {'language': 'mk', 'name': 'Macedonian'}, {'language': 'mg', 'name': 'Malagasy'}, {'language': 'ms', 'name': 'Malay'}, {'language': 'ml', 'name': 'Malayalam'}, {'language': 'mt', 'name': 'Maltese'}, {'language': 'mi', 'name': 'Maori'}, {'language': 'mr', 'name': 'Marathi'}, {'language': 'mn', 'name': 'Mongolian'}, {'language': 'my', 'name': 'Myanmar (Burmese)'}, {'language': 'ne', 'name': 'Nepali'}, {'language': 'no', 'name': 'Norwegian'}, {'language': 'or', 'name': 'Odia (Oriya)'}, {'language': 'ps', 'name': 'Pashto'}, {'language': 'fa', 'name': 'Persian'}, {'language': 'pl', 'name': 'Polish'}, {'language': 'pt', 'name': 'Portuguese'}, {'language': 'pa', 'name': 'Punjabi'}, {'language': 'ro', 'name': 'Romanian'}, {'language': 'ru', 'name': 'Russian'}, {'language': 'sm', 'name': 'Samoan'}, {'language': 'gd', 'name': 'Scots Gaelic'}, {'language': 'sr', 'name': 'Serbian'}, {'language': 'st', 'name': 'Sesotho'}, {'language': 'sn', 'name': 'Shona'}, {'language': 'sd', 'name': 'Sindhi'}, {'language': 'si', 'name': 'Sinhala'}, {'language': 'sk', 'name': 'Slovak'}, {'language': 'sl', 'name': 'Slovenian'}, {'language': 'so', 'name': 'Somali'}, {'language': 'es', 'name': 'Spanish'}, {'language': 'su', 'name': 'Sundanese'}, {'language': 'sw', 'name': 'Swahili'}, {'language': 'sv', 'name': 'Swedish'}, {'language': 'tg', 'name': 'Tajik'}, {'language': 'ta', 'name': 'Tamil'}, {'language': 'tt', 'name': 'Tatar'}, {'language': 'te', 'name': 'Telugu'}, {'language': 'th', 'name': 'Thai'}, {'language': 'tr', 'name': 'Turkish'}, {'language': 'tk', 'name': 'Turkmen'}, {'language': 'uk', 'name': 'Ukrainian'}, {'language': 'ur', 'name': 'Urdu'}, {'language': 'ug', 'name': 'Uyghur'}, {'language': 'uz', 'name': 'Uzbek'}, {'language': 'vi', 'name': 'Vietnamese'}, {'language': 'cy', 'name': 'Welsh'}, {'language': 'xh', 'name': 'Xhosa'}, {'language': 'yi', 'name': 'Yiddish'}, {'language': 'yo', 'name': 'Yoruba'}, {'language': 'zu', 'name': 'Zulu'}, {'language': 'he', 'name': 'Hebrew'}, {'language': 'zh', 'name': 'Chinese (Simplified)'}];
    static DEFAULT_VISION_FEATURES = {'LABEL_DETECTION':0.75, 'FACE_DETECTION':0.5, 'LANDMARK_DETECTION':0.75, 'LOGO_DETECTION':0.75, 'IMAGE_PROPERTIES':0.1, 'TEXT_DETECTION':0.0, 'OBJECT_LOCALIZATION':0.75};
    
    static _data = {};
    static _changed = {};

    static load(callback=null) {
        RemoteClient.cmd('load_settings',{},function(data){
            Settings._data = data;
            if (callback != null)
                callback();
        });
    }

    static save(callback=null) {
        if (Settings.changed) {
            RemoteClient.cmd('save_settings',Settings._changed,callback);
            Settings._changed = {};
            $(window).off('beforeunload');
        }
    }

    static get changed(){
        return Object.keys(Settings._changed).length > 0;
    }

    static get (key) {
        return Settings._data[key];
    }

    static set (key,value) {
        if (!Helper.object_equals(value,Settings.get(key)))
            Settings._changed[key] = value;
        else
            delete Settings._changed[key];
        $(window).trigger("settings_changed");
        if (Settings.changed)
            $(window).on('beforeunload', function(){return null;});
        else
            $(window).off('beforeunload');
    }

    static discard_changes() {
        //TODO update fields
        Settings._changed = {};
        $(window).off('beforeunload');
    }

    static create_filelist(key,rows=5,multiple=true,modifyable=true) {
        var select = $('<select>',{id:key,size:rows}).prop("multiple", multiple);
        for (var idx in Settings.get(key))
            select.append($('<option>').text(Settings.get(key)[idx]));
        if (modifyable) {
            var addpath = Settings.create_button('Add path',function(){
                            var inputpath = $('<input>',{type:"text",placeholder:"Type in path..."}).css("width","100%");
                            var valid = false;
                            new Dialog('dialog-settings-addpath','Add path',inputpath,function() {
                                if (inputpath.val().trim()) {
                                    RemoteClient.cmd('path_exists',inputpath.val().trim(),function(data){
                                        var path = data.data;
                                        if (path.exists && path.isdir) {
                                            select.append($('<option>').text(path.abspath));
                                            var paths = select.find('option').map((index, option) => option.value).get();
                                            Settings.set(key,paths);
                                            valid = true;
                                            return;
                                        } else if (path.isfile){
                                            new Popup("Path is a file, not a folder",path.abspath);
                                        } else {
                                            new Popup("Path doesn't exist",path.abspath);
                                        }
                                        valid = false;
                                    });
                                } else {
                                    new Popup("","You have to enter an existing path.");
                                    valid = false;
                                }
                                return valid;
                            });
                        });
            var remove = Settings.create_button('Remove',function(){
                            select.find('option:selected').remove()
                            var paths = select.find('option').map((index, option) => option.value).get();
                            Settings.set(key,paths);
                            $(this).prop('disabled',true);
                        }).prop('disabled',true);
            select.on('change',function(){
                remove.prop('disabled',select.find('option:selected').length == 0);
            })
            return select.add('<br/>').add(addpath).add(remove);
        }
        return select
    }

    static create_file(key) {
        return $('<input/>',{id:key,type:"text"})
                .val(Settings.get(key))
                .on('change',function(){
                    var input = $(this);
                    if (input.val()) {
                        RemoteClient.cmd('path_exists',input.val(),function(data){
                            var path = data.data;
                            if (path.exists && path.isfile) {
                                Settings.set(key,path.abspath);
                                input.val(path.abspath);
                            } else if (path.isdir)
                                new Popup("Path is a folder, not a file",path.abspath);
                            else
                                new Popup("Path doesn't exist",path.abspath); 
                        });
                    }
                });
    }

    static create_gapi(key,type='apikey',valid=false) {
        return $('<input/>',{id:key,type:"text"})
                .val(Settings.get(key))
                .toggleClass('valid',valid)
                .toggleClass('invalid',!valid)
                .on('focusin',function(){
                    var input = $(this);
                    input.data('val',input.val());
                })
                .on('change',function(){
                    var input = $(this);
                    if (input.val()) {
                        RemoteClient.cmd('check_'+type,input.val(),function(data){
                            var path = data;
                            if (path.valid) {
                                Settings.set(key,path.abspath);
                                input.val(path.abspath).addClass('valid').removeClass('invalid');
                            } else if (path.isdir){
                                new Popup("Path is a folder, not a file",path.abspath);
                                input.addClass('invalid').removeClass('valid');
                            } else if (!path.exists) {
                                new Popup("Path doesn't exist",path.abspath);
                                input.addClass('invalid').removeClass('valid');
                            } else {
                                new Popup("No valid "+type+".","Ensure you enabled the following APIs: Cloud Vision API, Geocoding API, and Cloud Translation API.");
                                input.addClass('invalid').removeClass('valid');
                            }
                        });
                    } else
                        input.addClass('invalid').removeClass('valid');
                });
    }

    static create_language(key) {
        var select = $('<select>',{id:key});
        for (var idx in Settings.SUPPORTED_LANGUAGES)
            select.append($('<option>',{value:Settings.SUPPORTED_LANGUAGES[idx]['language']})
                            .text(Settings.SUPPORTED_LANGUAGES[idx]['name'])
                            .attr("selected", Settings.SUPPORTED_LANGUAGES[idx]['language'] == Settings.get('translate')))
                  .on('change',function(){Settings.set(key,$(this).val());});
        
        return select
    }

    static create_textarea(key,rows=5) {
        return $('<textarea>',{id:key,rows:rows})
                .val(Settings.get(key))
                .on('change',function(){Settings.set(key,$(this).val());});
    }

    static create_input(key) {
        return $('<input/>',{id:key,type:"text"})
                .val(Settings.get(key))
                .on('change',function(){Settings.set(key,$(this).val());});
    }

    static create_regex(key) {
        return $('<input/>',{id:key,type:"text"})
                .val(Settings.get(key))
                .on('focusin',function(){
                    var input = $(this);
                    input.data('val',input.val());
                })
                .on('change',function(){
                    var input = $(this);
                    try {
                        new RegExp(input.val());
                        Settings.set(key,input.val());
                    } catch(e) {
                        new Popup("Invalid regular expression", '"'+input.val()+'" is no valid regular expression.')
                        input.val(input.data('val'));
                    }
                });
    }

    static create_number(key,min=null,max=null,step=null) {
        return $('<input/>',{id:key,type:"number",min:min,max:max,step:step})
                .val(Settings.get(key))
                .on('change',function(){
                    var input = $(this);
                    var value = parseFloat(input.val());
                    if (step != null)
                        value = Math.round(value / step) * step
                    if (min != null)
                        value = Math.max(value,min);
                    if (max != null)
                        value = Math.min(value,max);
                    input.val(value);
                    Settings.set(key,value);
                });
    }

    static create_checkbox(key,label=null) {
        var checkbox = $('<input/>',{id:key,type:"checkbox",name:key})
                .prop('checked', !!Settings.get(key))
                .on('change',function(){Settings.set(key,$(this).prop("checked"));});
        if (label)
            checkbox=checkbox.add($('<label>',{'for':key}).append(label));
        return checkbox
    }

    static create_button(title,fun) {
        return $('<input/>',{type:"button",value:title}).on('click',fun);
    }

    static create_visionfeatures(key) {
        var visionfeature = function(key,feature,default_value,features) {
            return $('<div>',{id:key,"class":"visionfeature"})
                     .append($('<input/>',{type:"checkbox","class":"feature-enabled",id:feature+"_checkbox"})
                                .prop('checked', feature in features)
                                .on('change',function(){
                                    var checkbox = $(this);
                                    if (checkbox.prop("checked"))
                                        features[feature] = parseFloat(checkbox.nextAll('.feature-threshold').val());
                                    else
                                        delete features[feature];
                                    Settings.set(key,features);
                                }))
                     .append($('<label>',{"class":"feature-name","for":feature+"_checkbox"}).append(feature.replace('_',' ').capitalize()))
                     .append($('<input/>',{type:"number","class":"feature-threshold",min:0,max:1,step:0.01})
                                .val((feature in Settings.get(key)) ? Settings.get(key)[feature] : default_value)
                                .on('change',function(){
                                    var input = $(this);
                                    var value = Math.max(Math.min(Math.round(parseFloat(input.val()) / 0.01) * 0.01,1),0).toFixed(2);
                                    input.val(value);
                                    if (feature in features) {
                                        features[feature] = value;
                                        Settings.set(key,features);
                                    }
                                }));
        }
        var features = $();
        var values = {...Settings.get(key)};
        for (var feature in Settings.DEFAULT_VISION_FEATURES)
            features = features.add(visionfeature(key,feature,Settings.DEFAULT_VISION_FEATURES[feature],values));
        return features
    }
}

class RemoteClient {
    static ws_retry_attempts = 3;
    static ws = null;
    static _callbacks = {};

    static add_callback(cmds,fun=function(data){}) {
        cmds = cmds.split(' ');

        cmds.forEach(function(cmd){
            if (!(cmd in RemoteClient._callbacks)) {
                RemoteClient._callbacks[cmd] = [];
            }
            RemoteClient._callbacks[cmd].push(fun);
        });
    }

    static remove_callbacks() {
        RemoteClient._callbacks = {};
    }
    
    static ws_connect() {
        let url=new URL(window.location.href);
        let wsurl;
        if (url.protocol == "http:")
            wsurl = "ws://"+url.host+"/ws";
        else if (url.protocol == "https:")
            wsurl = "wss://"+url.host+"/ws";
            
        if (wsurl) {
            RemoteClient.ws = new WebSocket(wsurl);
            RemoteClient.ws.onmessage = function(evt){
                try {
                    let data = JSON.parse(evt.data);
                    if (data.cmd in RemoteClient._callbacks) {
                        RemoteClient._callbacks[data.cmd].forEach(function(fun){
                            fun(data.data);
                        });
                    }
                }
                catch(err) {
                    console.error('Failed to handle websocket event: ' + err.message);
                    console.log(evt.data);
                }
            }
            RemoteClient.ws.onopen = function(evt) {
                RemoteClient.ws_retry_attempts = 3;
                console.info('Websocket connection established to '+wsurl);
            }
            RemoteClient.ws.onerror = function(evt) {
                console.error("WebSocket error observed:", evt);
            }
            RemoteClient.ws.onclose = function(event) {
                if (RemoteClient.retry_attempts > 0) {
                    RemoteClient.retry_attempts -= 1;
                    console.warn('WebSocket connection closed, trying to reconnect in 5 seconds.');
                    setTimeout(RemoteClient.ws_connect,5000);
                } else {
                    console.error('WebSocket connection closed, failed to reconnect.');
                    new Popup("WebSocket connection closed.","You won't get instant updates");
                }
            }
        }
    }

    static get ws_connected(){
        return (RemoteClient.ws && RemoteClient.ws.readyState == WebSocket.OPEN);
    }

    static cmd(cmd,data={},sync_callback=null) {
        if (RemoteClient.ws_connected && sync_callback == null) {
            RemoteClient.ws.send(JSON.stringify({cmd:cmd,data:data}));
        } else {
            $.post( "/api/"+cmd+"/", {data: JSON.stringify(data)}, function(data) {
                try {
                    if (sync_callback == null) {
                        if (data.cmd in RemoteClient._callbacks) {
                            RemoteClient._callbacks[data.cmd].forEach(function(fun){
                                fun(data.data);
                            });
                        }
                    } else {
                        sync_callback(data.data);
                    }
                }
                catch(err) {
                    console.error('Failed to handle api response: ' + err.message);
                }
            })
            .fail(function() {
                console.error( "Failed to execute '"+cmd+"': server error, try again." );
            });
        }
    }
}

class Helper {
    static object_equals( x, y ) {
        if ( x === y ) return true;
        if ( ! ( x instanceof Object ) || ! ( y instanceof Object ) ) return false;
        if ( x.constructor !== y.constructor ) return false;
        for ( var p in x ) {
          if ( ! x.hasOwnProperty( p ) ) continue;
          if ( ! y.hasOwnProperty( p ) ) return false;
          if ( x[ p ] === y[ p ] ) continue;
          if ( typeof( x[ p ] ) !== "object" ) return false;
          if ( ! Helper.object_equals( x[ p ],  y[ p ] ) ) return false;
        }
        for (var p in y )
          if ( y.hasOwnProperty( p ) && ! x.hasOwnProperty( p ) )
            return false;
        return true;
    }

    static disableContextMenu() {
        $(document).on("contextmenu",function(e) {
            e.preventDefault();
            e.stopPropagation();
        });
    }

    static fileSizeReadable(sizeInBytes) {
        var units = [' B',' KB',' MB',' GB',' TB',' PB',' EB',' ZB'];
        for (var i=0; i<units.length; i++){
            if (Math.abs(sizeInBytes) < 1000.0)
                return sizeInBytes.toFixed(2) + units[i];
            sizeInBytes /= 1024.0;
        }
        
        return sizeInBytes.toFixed(2) + ' YB';
    }

    static some_hacks() {
        jQuery.ui.autocomplete.prototype._resizeMenu = function () {
          var ul = this.menu.element;
          ul.outerWidth(this.element.outerWidth());
        }
        $.event.special.widthChanged = {
            remove: function() {
                $(this).children('iframe.width-changed').remove();
            },
            add: function () {
                var elm = $(this);
                var iframe = elm.children('iframe.width-changed');
                if (!iframe.length) {
                    iframe = $('<iframe/>').addClass('width-changed').prependTo(this);
                }
                var oldWidth = elm.width();
                function elmResized() {
                    var width = elm.width();
                    if (oldWidth != width) {
                        elm.trigger('widthChanged', [width, oldWidth]);
                        oldWidth = width;
                    }
                }
    
                var timer = 0;
                var ielm = iframe[0];
                (ielm.contentWindow || ielm).onresize = function() {
                    clearTimeout(timer);
                    timer = setTimeout(elmResized, 20);
                };
            }
        }
        
        $.event.special.swipe = {
            remove: function() {
                
            },
            add: function () {
                var points = [];
                var threshold = 150; //min swipe distance
                var allowedTime = 300; // maximum swipe time

                this.addEventListener('touchstart', function(e){
                    var finger = e.changedTouches[0];
                    points.push({x:finger.pageX,y:finger.pageY,time:new Date().getTime()})
                    //e.preventDefault();
                }, {passive: false}, false);
              
                this.addEventListener('touchmove', function(e){
                    //e.preventDefault();
                }, {passive: false}, false);
              
                this.addEventListener('touchend', function(e){
                    var touchobj = e.changedTouches[0];
                    var point = points.shift(); 
                    var distX = touchobj.pageX - point.x;
                    var distY = touchobj.pageY - point.y;
                    var elapsedTime = new Date().getTime() - point.time;
                    var direction = null;

                    if (elapsedTime <= allowedTime){
                        if (Math.abs(distX) >= threshold && Math.abs(distY) <= Math.abs(distX))
                            direction = (distX < 0) ? 'left' : 'right';
                        else if (Math.abs(distY) >= threshold && Math.abs(distX) <= Math.abs(distY))
                            direction = (distY < 0) ? 'up' : 'down';
                    }
                    if (direction != null){
                        $(this).trigger('swipe', direction);
                        e.preventDefault();
                    }
                }, {passive: false}, false);
            }
        }
        
        $.fn.isHScrollable = function () {
            return this[0].scrollWidth > this[0].clientWidth;
        };
        $.fn.isVScrollable = function () {
            return this[0].scrollHeight > this[0].clientHeight;
        };
        $.fn.isScrollable = function () {
            return this[0].scrollWidth > this[0].clientWidth || this[0].scrollHeight > this[0].clientHeight;
        };
        String.prototype.capitalize = function() {
            return this.charAt(0).toUpperCase() + this.substring(1).toLowerCase();
        }
        Number.prototype.countDecimals = function () {
            if(Math.floor(this.valueOf()) === this.valueOf()) return 0;
            return this.toString().split(".")[1].length || 0; 
        }
    }

    static urlParam(name){
        var results = new RegExp('[\?&]' + name + '=([^&#]*)').exec(window.location.href);
        if (results==null) return null;
        return decodeURI(results[1]) || 0;
    }
}

class Html {
    static row() {
        var row = $('<div>',{"class": "row"})
        for (var i = 0; i < arguments.length; i++)
            row.append($('<div>',{"class": "col col"+(i+1)}).append(arguments[i]))
        return row
    }

    static table(title,subheader='') {
        var table = $('<div>',{"class":"table"}).append($('<div>',{"class":"header"}).html(title));
        if (subheader)
            table.append($('<div>',{"class":"subheader"}).html(subheader));
        return table
    }
}

class Page {
    constructor(id) {
        this.menu = new Menu();
        this.header = new Header('header');
        this.progress = $('<div>',{id:"progress"});
        this.footer = new Header('footer');
        this.footer.right.append(this.progress);
        this.content = $('<div>',{id:id,"class":"content"}).appendTo('body');
        this.addResponseHandler();
    }

    addResponseHandler() {
        var page = this;
        RemoteClient.add_callback('new_log_entry',function(data) {
            new Popup('New log entry',data[1]);
        });
        RemoteClient.add_callback('remaining_files',function(data) {
            if (data == 1)
                page.progress.html(data+' file in queue');
            else
                page.progress.html(data+' files in queue');
        });
        RemoteClient.add_callback('save_settings',function(data) {
            Settings._data = data;
            new Popup('','Settings changed.');
        });
        RemoteClient.add_callback('new_faces', data => new Popup('','New faces found.'));
        RemoteClient.add_callback('name_faces ignore_faces delete_faces', data => new Popup('','Faces updated.'));
        RemoteClient.add_callback('process', data => new Popup('Scanning paths...','Annotation will start afterwards.'));
    }

    static Annotation = class extends Page {
        constructor() {
            super('annotation');
            this.menu.add_default();
            this.show();
        }

        show() {
            var annotation = this;
            var filelist = Settings.create_filelist("paths",5,true,false)
                    .on('change',function() {
                        annotation.btn_save.prop("disabled",$(this).val().length == 0);
                    })
                    annotation.content.append(
                Html.table("Annotation").addClass('settings')
                    .append(Html.row('Select paths',filelist))
                    .append(Html.row('Reannotate files',Settings.create_checkbox('reannotate')))
                    .append(Html.row('Remove EXIF orientation',Settings.create_checkbox('rotate_images')))
                    .append(Html.row('Replace labels',Settings.create_checkbox("replace_labels")))
                    .append(Html.row('Translate labels',Settings.create_language("translate")))
                    .append(Html.row('Reverse geocoding',Settings.create_checkbox("reverse_geocoding")))
                    .append(Html.row("Vision Features",Settings.create_visionfeatures("vision_features")))
                );
            
                annotation.btn_save = Settings.create_button('Start',() => annotation.process()).prop("disabled",true).appendTo(annotation.footer.left);
        }

        process() {
            var selectedpaths = this.content.find('#paths').val()
            if (selectedpaths.length) {
                var data = {...Settings._data, ...Settings._changed};
                RemoteClient.cmd('process',{
                    paths: selectedpaths,
                    vision_features: data.vision_features,
                    whitelist: data.whitelist,
                    blacklist: data.blacklist,
                    translate: data.translate,
                    replace_labels: data.replace_labels,
                    rotate_images: data.rotate_images,
                    reannotate: data.reannotate,
                    blocking: false
                });
                this.content.find('#paths').val([]).trigger('change');
            }
        }
    }

    static ImageList = class extends Page {
        constructor(itemclass) {
            super(itemclass+'-container');
            var imagelist = this;

            imagelist.itemclass = itemclass;
            imagelist.content.addClass('image-list').on('click', () => $('.'+itemclass).trigger('unselect'));

            imagelist.zoom_slider = $('<div>',{id:'zoom-slider'}).appendTo(imagelist.footer.left).slider({
                value: imagelist.zoom,
                min: 0.5,
                max: 2.5,
                step: 0.01,
                slide: function(event, ui) {
                    imagelist.zoom = ui.value;
                    $(window).trigger('zoom');
                }
            });

            $(document).on('keydown',function(evt) {
                if (!Overlay.any_visible) {
                    var key = (evt.which || evt.keyCode);
                    //console.log(key)
                    if(key == 16 || key == 17) { //shift or ctrl
                        imagelist.content.find('.'+imagelist.itemclass).addClass('ctrlPressed').find('input[type="text"]').prop('disabled',true);;
                    }
                    if(evt.ctrlKey && key == 65) {//ctrl+a
                        imagelist.content.find('.'+imagelist.itemclass).trigger('select');
                        evt.preventDefault();
                    }
                    if(key == 27) {//esc
                        imagelist.content.find('.'+imagelist.itemclass).trigger('unselect').removeClass('focused');
                        evt.preventDefault();
                    }
                }
            }).on('keyup',function(evt){
                var key = (evt.which || evt.keyCode) ;
                if(key == 16 || key == 17) { //shift or ctrl
                    imagelist.content.find('.'+imagelist.itemclass).removeClass('ctrlPressed').find('input[type="text"]').prop('disabled',false);
                }
            });
        }

        get zoom() {
            if (!('_zoom' in this))
                this.zoom = Cookies.get(this.itemclass+'-zoom') || 1.0;
            return this._zoom;
        }

        set zoom(value) {
            this._zoom = parseFloat(value);
            $('.'+this.itemclass+', .ui-autocomplete').css('zoom',this._zoom);
            Cookies.set(this.itemclass+'-zoom',value);
        }

        static Image = class {
            constructor(parent,img_index,img_src,fullimg_src,force_reload=false) {
                this.imagelist = parent;
                this.img_index = img_index;
                this.img_src = img_src;
                this.fullimg_src = fullimg_src;
                this.force_reload = force_reload;
                
                this.elem = $('<div>', {imageindex: this.img_index, "class": this.imagelist.itemclass+" image-list-item"}).css('zoom',this.imagelist.zoom).data('obj',this);
                this.checkbox = $('<input />', {type: 'checkbox',"class": 'checkbox'}).appendTo(this.elem);
                this.img = $('<img />', {src: this.img_src + ((this.force_reload) ? "?" + new Date().getTime() : "")}).appendTo($('<div>',{'class':'img_wrapper'}).appendTo(this.elem));
                
                var image = this;
                image.elem.on('select',()=>image.select())
                        .on('unselect',()=>image.unselect())
                        .on('toggle',()=>image.toggle())
                        .on('fullimage',()=>image.fullimage.show())
                        .on("click", function (evt) {
                            if (evt.ctrlKey) {
                                image.toggle();
                            }
                            if (evt.shiftKey) {
                                if (image.elem.prevAll('.'+image.imagelist.itemclass+'.focused').length) {
                                    image.elem.siblings('.'+image.imagelist.itemclass+'.focused').trigger('select');
                                    image.elem.prevUntil('.'+image.imagelist.itemclass+'.focused','.'+image.imagelist.itemclass).trigger('select');
                                } else if (image.elem.nextAll('.'+image.imagelist.itemclass+'.focused').length) {
                                    image.elem.siblings('.'+image.imagelist.itemclass+'.focused').trigger('select');
                                    image.elem.nextUntil('.'+image.imagelist.itemclass+'.focused','.'+image.imagelist.itemclass).trigger('select');
                                }
                                image.select();
                            }
                            image.focus();
                            evt.stopPropagation();
                        });

                image.img.on('click',function(evt){
                            if (!evt.ctrlKey && !evt.shiftKey){
                                image.fullimage.show();
                                evt.stopPropagation();
                            }});

                image.checkbox.on('click',function(evt){
                    if (!evt.ctrlKey && !evt.shiftKey){
                        image.focus();
                        image.toggle();
                        evt.stopPropagation();
                    }
                });
            }

            focus() {
                $('.'+this.imagelist.itemclass+'.focused').removeClass('focused');
                this.elem.addClass('focused').trigger('focused');
            }

            select() {
                this.elem.addClass("selected");
                this.checkbox.prop('checked', true);
            }

            unselect() {
                this.elem.removeClass("selected");
                this.checkbox.prop('checked', false);
            }

            toggle() {
                if (this.is_selected)
                    this.unselect();
                else
                    this.select();
            }

            next() {
                if (this.elem.next('.'+this.imagelist.itemclass).length) {
                    return this.elem.next('.'+this.imagelist.itemclass).data('obj');
                } else {
                    return this;
                }
            }

            prev() {
                if (this.elem.prev('.'+this.imagelist.itemclass).length) {
                    return this.elem.prev('.'+this.imagelist.itemclass).data('obj');
                } else {
                    return this;
                }
            }

            get is_selected() {
                return this.elem.hasClass("selected");
            }

            get is_last() {
                return this == $('.'+this.imagelist.itemclass).last().data('obj');
            }

            get fullimage() {
                var image = this;
                image.focus();
                if (!('_fullimage' in image)) {
                    image._fullimage = new Overlay($('<div>',{"class":"fullimage"}).append($('<img />', {src: image.fullimg_src + ((this.force_reload) ? "?" + new Date().getTime() : "")})),true,'',
                        function(evt) {
                            var key = (evt.which || evt.keyCode) ;
                            if(key == 39 || key == 40) { //arrow right/down
                                image.fullimage.hide();
                                image.next().fullimage.show();
                                evt.preventDefault();
                            }
                            if(key == 37 || key == 38) { //arrow left/up
                                image.fullimage.hide();
                                image.prev().fullimage.show();
                                evt.preventDefault();
                            }
                        });
                    image._fullimage.elem.on('swipe',function(e,swipedir){
                            image.fullimage.hide();
                            if (swipedir=='left') {
                                image.next().fullimage.show();
                            }
                            else if (swipedir=='right') {
                                image.prev().fullimage.show();
                            } 
                            e.stopPropagation();
                            e.preventDefault()
                        });
                }
                return image._fullimage;
            }
        }
    }

    static Duplicates = class extends Page.ImageList {

        constructor() {
            super('duplicate');
            var duplicates = this;
            duplicates.menu.add_default();

            duplicates.content.on('swipe',function(e,swipedir){
                if (swipedir=='left')
                    duplicates.next_group();
                else if (swipedir=='right')
                    duplicates.prev_group();
                });
            duplicates.list = $('<div>',{id:"duplicate-list"}).insertBefore(duplicates.content);
            
            var offset = 500;
            var lastScrollTop = 0;
            duplicates.list.on('scroll',function(e) {
                var elem = $(e.currentTarget);
                var st = $(this).scrollTop();
                if(st != lastScrollTop) {
                    if ((elem[0].scrollHeight - elem.scrollTop() < elem.outerHeight() + offset)) {
                        duplicates.load_next();
                    }
                }
                else {
                    if ((elem[0].scrollWidth - elem.scrollLeft() < elem.outerWidth() + offset)) {
                        duplicates.load_next();
                    }
                }
                lastScrollTop = st;
            });
            $(window).on('resize',() => duplicates.list.scrollTo('.group-item.selected'));

            duplicates.similarity_select = $('<select>',{id:"duplicate_similarity"}).on('change',()=>duplicates.similarity = duplicates.similarity_select.val());
            [90,91,92,93,94,95,96,97,98,99,100].forEach(value => duplicates.similarity_select.append($('<option>',{value:value/100}).attr('selected',value/100==duplicates.similarity).append(value+"%")));
            duplicates.header.right.append($('<label>',{"for": "duplicate_similarity"}).append('Similarity:'));
            duplicates.header.right.append(duplicates.similarity_select);

            duplicates.btn_keep = $('<input />', {type: 'image', src: '/web/greentick.png', alt: 'Keep all', title: 'Keep all'}).appendTo(duplicates.header.right).on('click',function(evt){
                duplicates.keep_all();
                evt.stopPropagation();
            });
            duplicates.btn_delete = $('<input />', {type: 'image', src: '/web/redcross.png', alt: 'Delete all', title: 'Delete all'}).appendTo(duplicates.header.right).on('click',function(evt){
                duplicates.delete_all();
                evt.stopPropagation();
            });
            
            duplicates.addKeyDownEvents();

            duplicates.selected_group = -1;
            duplicates.load(duplicates.similarity);
        }

        get similarity() {
            if (!('_similarity' in this))
                this._similarity = parseFloat(Cookies.get('similarity')) || 1.0;
            return this._similarity;
        }

        set similarity(value) {
            this._similarity = parseFloat(value);
            Cookies.set('similarity',value);
            this.load(this._similarity);
        }

        addResponseHandler(){
            super.addResponseHandler();

            var duplicates = this;
            RemoteClient.add_callback('load_duplicates',function(data) {
                duplicates.set_duplicates(data.order,data.groups);
                GUI.loading.hide();
            });
            
            RemoteClient.add_callback('delete_duplicates',() => GUI.loading.hide());
            
            RemoteClient.add_callback('keep_duplicates',function(images) {
                images.forEach(imgindex => duplicates.deleted_image(imgindex));
                GUI.loading.hide();
            });

            RemoteClient.add_callback('deleted_image', imgindex => duplicates.deleted_image(imgindex));
        }

        deleted_image(imgindex) {
            var duplicates = this;

            duplicates.groupids.forEach(function(groupid){
                duplicates.groups[groupid].forEach(function(image,idx2,group){
                    if (image.index == imgindex)
                        group.splice(idx2, 1);
                });
                if (duplicates.groups[groupid].length == 1) {
                    delete duplicates.groups[groupid]
                    var index = duplicates.groupids.indexOf(groupid);
                    if (index > -1)
                        duplicates.groupids.splice(index, 1);
                    duplicates.list.find('.group-wrapper .group-item[groupid="'+groupid+'"]:not(.selected)').parent().remove();
                    duplicates.last_group -= 1;
                    duplicates.num_groups -= 1;
                }
            });
            
            duplicates.content.find('.duplicate[imageindex="'+imgindex+'"]').remove();
            if (duplicates.content.find('.duplicate').length <= 1){
                var selected_group = duplicates.list.find('.group-wrapper .group-item.selected').parent();
                duplicates.next_group();
                selected_group.remove();
            }
        }

        load(similarity=0.99) {
            RemoteClient.cmd('load_duplicates',{similarity:similarity});
            GUI.loading.show();
        }

        load_next(num_groups=10) {
            var duplicates = this;
            duplicates.groupids.slice(duplicates.last_group,duplicates.last_group+num_groups).forEach(function(groupid){
                duplicates.create_group(groupid);
            });
            duplicates.last_group += num_groups;
            if (!duplicates.list.isScrollable() && duplicates.last_group < duplicates.num_groups)
                duplicates.load_next();
        }

        select_group(groupid=null) {
            var duplicates = this;
            if (groupid==null)
                duplicates.list.find('.group-wrapper:first-child .group-item').trigger('click');
            else
                duplicates.list.find('.group-wrapper .group-item[groupid="'+groupid+'"]').trigger('click');
            duplicates.list.scrollTo('.group-item.selected')
        }

        prev_group() {
            this.list.scrollTo(this.list.find('.group-item.selected').parent().prev().find('.group-item').trigger('click'));
        }

        next_group() {
            this.list.scrollTo(this.list.find('.group-item.selected').parent().next().find('.group-item').trigger('click'));
        }

        create_group(groupid) {
            var duplicates = this;
            
            duplicates.list.append(
                $('<div>',{"class": "group-wrapper"}).append(
                    $('<div>',{"class": "group-item", groupid: groupid}).append(
                        $('<img>',{src: duplicates.groups[groupid][0].src})
                    ).on('click',function(){
                        duplicates.list.find('.group-item.selected').removeClass('selected');
                        $(this).addClass('selected');
                        duplicates.selected_group = groupid;
                        duplicates.content.empty();
                                            
                        duplicates.groups[groupid].forEach(function(image){
                            var item = new Page.Duplicates.Duplicate(duplicates,image.index,image.src,groupid,image.file_path,image.file_name,image.size,image.date);
                            duplicates.content.append(item.elem);
                        });
                        duplicates.content.find('.duplicate:not(:first-child)').trigger('select')
                    })
                )
            );
        }

        set_duplicates(order,groups) {
            if (order.length == 0)
                new Popup('','No duplicates found with a similarity of '+this.similarity*100+'%');
            this.list.empty();
            this.content.empty();
            this.groupids = order;
            this.groups = groups;
            this.num_groups = this.groupids.length;
            this.last_group = 0;
            this.load_next();
            this.select_group();
        }


        addKeyDownEvents() {
            var duplicates = this;
            $(document).on('keydown',function(evt) {
                if (!Overlay.any_visible) {
                    var key = (evt.which || evt.keyCode) ;
                    if(key == 39 || key == 40) { //arrow right/down
                        duplicates.next_group();
                        evt.preventDefault();
                    }
                    if(key == 37 || key == 38) { //arrow left/up
                        duplicates.prev_group();
                        evt.preventDefault();
                    }
                    if(key == 46) {//del
                        duplicates.delete_selected();
                        evt.preventDefault();
                    }
                }
            });
        }

        get_selected() {
            var data = [];
            var dom_selected = $('.duplicate.selected');
            dom_selected.each(function() { data.push(parseInt($(this).attr('imageindex')));});
            return [data,dom_selected]
        }

        delete_selected() {
            var duplicates = this;
            var [selected,dom_selected] = duplicates.get_selected();
            if (dom_selected.length > 0) {
                var duplicatestring = (dom_selected.length == 1) ? "selected duplicate" : dom_selected.length + " selected duplicates";
                new Dialog("dialog-duplicates-delete","Delete Duplicates",'Do you want to delete the '+ duplicatestring + '? This can not be undone!', function() {
                    RemoteClient.cmd('delete_duplicates',{images:selected});
                    GUI.loading.show();
                    return true;
                }, function() {
                    if (dom_selected.length == 1)
                        dom_selected.trigger('unselect');
                    return true;
                },true);
            }
        }

        delete_all() {
            var duplicates = this;
            var imgidxs=[];
            duplicates.groupids.forEach(function(groupid){
                imgidxs=imgidxs.concat(duplicates.groups[groupid].slice(1).map(x=>x.index));
            });
            imgidxs = Array.from(new Set(imgidxs));
            new Dialog("dialog-duplicates-deleteall","Delete all duplicates",'Do you want to delete all '+ imgidxs.length +' duplicates with a similarity of '+ this.similarity*100 + '%? This can not be undone!', function() {
                RemoteClient.cmd('delete_duplicates',{images:imgidxs});
                GUI.loading.show();
                return true;
            });
        }

        keep_selected() {
            var duplicates = this;
            var [selected,dom_selected] = duplicates.get_selected();
            if (dom_selected.length > 0) {
                var duplicatestring = (dom_selected.length == 1) ? "selected duplicate" : dom_selected.length + " selected duplicates";
                new Dialog("dialog-duplicates-keep","Keep Duplicates",'Do you want to keep the '+ duplicatestring + '? This can only be undone by rescanning the images.', function() {
                    RemoteClient.cmd('keep_duplicates',{images:selected});
                    GUI.loading.show();
                    return true;
                }, function() {
                    if (dom_selected.length == 1)
                        dom_selected.trigger('unselect');
                    return true;
                },true);
            }
        }

        keep_all() {
            var duplicates = this;
            var imgidxs=[];
            duplicates.groupids.forEach(function(groupid){
                imgidxs=imgidxs.concat(duplicates.groups[groupid].map(x=>x.index));
            });
            imgidxs = Array.from(new Set(imgidxs));
            new Dialog("dialog-duplicates-keepall","Keep all duplicates",'Do you want to keep all '+ imgidxs.length +' duplicates with a similarity of '+ this.similarity*100 + '%? This can only be undone by rescanning the images.', function() {
                RemoteClient.cmd('keep_duplicates',{images:imgidxs});
                GUI.loading.show();
                return true;
            });
        }

        static Duplicate = class extends Page.ImageList.Image{
            constructor (duplicates,img_index,img_src,groupid,file_path,file_name,file_size,file_date,force_reload=false) {
                super(duplicates,img_index,img_src,img_src,force_reload);
                this.groupid = groupid;
                this.file_path = file_path;
                this.file_name = file_name;
                this.file_size = file_size;
                this.file_date = file_date;
                this.create();
            }

            create() {
                var duplicate = this;
                duplicate.elem.attr('groupid',duplicate.groupid);

                var size = Helper.fileSizeReadable(this.file_size);
                var date = new Date(this.file_date*1000);
                var dateString = date.toLocaleDateString("de-DE") + " " + date.toLocaleTimeString("de-DE"); //TODO

                duplicate.elem
                    .append($('<div>',{'class':'file_name','title':duplicate.file_path})
                            .append(duplicate.file_name))
                    .append($('<div>',{'class':'file_size'}).append(size))
                    .append($('<div>',{'class':'file_date'}).append(dateString))
                duplicate.btn_delete = $('<input />', {type: 'image', src: '/web/redcross.png', alt: 'Delete', title: 'Delete'}).on('click',function(evt){
                    if (!evt.ctrlKey && !evt.shiftKey){
                        duplicate.select();
                        duplicate.imagelist.delete_selected();
                        evt.stopPropagation();
                    }
                });
                duplicate.btn_keep = $('<input />', {type: 'image', src: '/web/greentick.png', alt: 'Keep', title: 'Keep'}).on('click',function(evt){
                    if (!evt.ctrlKey && !evt.shiftKey){
                        duplicate.select();
                        duplicate.imagelist.keep_selected();
                        evt.stopPropagation();
                    }
                });
                $('<div>').appendTo(duplicate.elem).append(duplicate.btn_keep).append(duplicate.btn_delete);
            }
        }
    }

    static Facetagger = class extends Page.ImageList {
        numfaces = 10;
        all_loaded = false;
        loading = false;
        faces = [];
        _known_names = [];

        constructor() {
            super('face');
            var facetagger = this;
            facetagger.menu.add_default();

            facetagger.content.on('widthChanged',() => facetagger.load_next(10));

            facetagger.facetype_select = $('<select>',{id:"face_type"}).on('change',()=>facetagger.facetype = facetagger.facetype_select.val());
            ['untagged','ignored','all'].forEach(type => facetagger.facetype_select.append($('<option>',{value:type}).attr('selected',type==facetagger.facetype).append(type)));
            facetagger.header.right.append($('<label>',{"for": "face_type"}).append('Facetype:'));
            facetagger.header.right.append(facetagger.facetype_select);
            
            facetagger.addKeyDownEvents();
            $(window).on('scroll zoom',() => facetagger.load_next(10));
            facetagger.load(facetagger.numfaces,facetagger.facetype);
        }

        get known_names() {
            var facetagger = this;
            if (!('_known_names' in facetagger) || facetagger._known_names.length == 0)
                RemoteClient.cmd('known_names',{}, data => facetagger.known_names = data);
            
            return facetagger._known_names;
        }

        set known_names(value) {
            this._known_names = value;
            $( ".face input[type='text']" ).autocomplete( "option", "source", value );
            $( ".ui-autocomplete" ).css('zoom',this.zoom);
        }

        get facetype() {
            if (!('_facetype' in this))
                this._facetype = Cookies.get('facetype') || 'untagged';
            return this._facetype;
        }

        set facetype(value) {
            this.load(this.numfaces,value);
            this._facetype = value;
            Cookies.set('facetype',value);
        }

        addResponseHandler() {
            super.addResponseHandler();
            var facetagger = this;
            RemoteClient.add_callback('load_faces',function(data) {
                if (data.length > 0) {
                    facetagger.create(data);
                    facetagger.loading = false;
                    facetagger.load_next(10);
                } else {
                    facetagger.loading = false;
                    facetagger.all_loaded = true;
                    if ($('.face').length == 0)
                        new Popup('','No '+((facetagger.facetype == "all")?"":facetagger.facetype)+' faces found');
                }
            });
            RemoteClient.add_callback('new_faces',data => facetagger.create(data,true));
            RemoteClient.add_callback('name_faces ignore_faces',function(data) {
                facetagger.update(data);
                GUI.loading.hide();
            });
            RemoteClient.add_callback('delete_faces',function(data) {
                facetagger.replace(data);
                GUI.loading.hide();
            });
            RemoteClient.add_callback('known_names',data => facetagger.known_names = data);
            RemoteClient.add_callback('deleted_image', imgindex => $('.face[imageindex="'+imgindex+'"]').remove()); //TODO seems not to work
        }

        load(numfaces,facetype,lastimageid=null,lastfaceid=null) {
            var facetagger = this;
            if (facetype != facetagger.facetype)
                facetagger.all_loaded = false;
            if (!facetagger.loading && !facetagger.all_loaded) {
                facetagger.loading = true;
                if (!lastimageid || facetype != facetagger.facetype){
                    //we have to add the widthChanged listener after empty()
                    facetagger.content.empty().on('widthChanged',() => facetagger.load_next(10));
                }
                facetagger.numfaces = numfaces;
                facetagger._facetype = facetype;
                RemoteClient.cmd('load_faces',{numfaces:numfaces,
                                               lastimageid:lastimageid,
                                               lastfaceid:lastfaceid,
                                               facetype:facetype});
            }
        }

        load_next(numfaces=null,force=false) {
            var facetagger = this;
            var offset = 500;
            if ($('.face').length) // load 5 rows in advance
                offset = 5 * $('.face').first().height() * facetagger.zoom;
            if (($(window).scrollTop() + window.innerHeight > $(document).height() - offset) || force) {
                var lastface = $('.face').last().data('obj');
                if (lastface !== undefined) {
                    if (!numfaces) numfaces = facetagger.numfaces;
                    facetagger.load(numfaces,
                                    facetagger.facetype,
                                    parseInt(lastface.img_index),
                                    parseInt(lastface.face_index));
                }
            }
        }

        create(data,reverse=false,force_reload=false){
            var facetagger = this;
            if (reverse)
                data = data.reverse();
            data.forEach(function(image){
                if (reverse)
                    image.faces = image.faces.reverse();
                image.faces.forEach(function(item) {
                    var face = new Page.Facetagger.Face(facetagger,image.index,image.src,item.index,item.src,item.name,item.ignored,force_reload);
                    if (!reverse)
                        facetagger.content.append(face.elem);
                    else
                        facetagger.content.find('> iframe').after(face.elem);
                })
            });
            
            $( ".ui-autocomplete" ).css('zoom',facetagger.zoom); //TODO
        }

        update(data){
            var facetagger = this;
            data.forEach(function(image){
                image.faces.forEach(function(item) {
                    var face = $('.face[imageindex="'+image.index+'"][faceindex="'+item.index+'"]').data('obj');
                    if (facetagger.facetype == 'all' || (face.ignored && facetagger.facetype == 'ignored')) {
                        if (item.length > 0) {
                            face.unselect();
                            face.input.val(face.name);
                            face.btn_ignore.toggle(!face.ignored);
                        }
                        else
                            facetagger.create([{index: image.index, src: image.src, faces: [item]}],true);
                    } else
                        face.elem.remove();
                });
                $('.face[imageindex="'+image.index+'"]').insertAfter(facetagger.content.find(" > iframe"));
            });
            facetagger.load_next(10);
        }

        replace(data){
            var facetagger = this;
            data.forEach(function(image){
                $('.face[imageindex="'+image.index+'"]').remove(); //TODO: update instead of delete and create
                
                image.faces.forEach(function(face) {
                    if (facetagger.facetype == 'all' || (face.ignored && facetagger.facetype == 'ignored') || (!face.ignored && face.name == '' && facetagger.facetype == 'untagged')) {
                        facetagger.create([{index: image.index, src: image.src, faces: [face]}],true,true);
                    }
                });
            });
            facetagger.load_next(10);
        }

        get_selected() {
            var data = {};
            var dom_selected = $('.face.selected');
            dom_selected.each(function(){
                if (data[$(this).attr('imageindex')])
                    data[$(this).attr('imageindex')].push(parseInt($(this).attr('faceindex')));
                else
                    data[$(this).attr('imageindex')] = [parseInt($(this).attr('faceindex'))];
            });
            return [data,dom_selected]
        }

        name_selected(name) {
            var facetagger = this;
            name = name.trim();
            var [selected,dom_selected] = facetagger.get_selected();
            if (dom_selected.length > 0 && name != "") {
                var facestring = (dom_selected.length == 1) ? "selected face" : dom_selected.length + " selected faces";
                new Dialog("dialog-faces-name","Name faces",'Do you want to set the name of the '+ facestring + ' to: "' + name+ '"?', function() {
                    RemoteClient.cmd('name_faces',{name:name,images:selected});
                    GUI.loading.show();
                    return true;
                }, function() {
                    if (dom_selected.length == 1)
                        dom_selected.trigger('unselect');
                    return true;
                },true);
            }
        }

        ignore_selected() {
            var facetagger = this;
            var [selected,dom_selected] = facetagger.get_selected();
            if (dom_selected.length > 0) {
                var facestring = (dom_selected.length == 1) ? "selected face" : dom_selected.length + " selected faces";
                new Dialog("dialog-faces-ignore","Ignore faces",'Do you want to ignore the '+ facestring + '?', function() {
                    RemoteClient.cmd('ignore_faces',{images:selected});
                    GUI.loading.show();
                    return true;
                }, function() {
                    if (dom_selected.length == 1)
                        dom_selected.trigger('unselect');
                    return true;
                },true);
            }
        }

        delete_selected() {
            var facetagger = this;
            var [selected,dom_selected] = facetagger.get_selected();
            if (dom_selected.length > 0) {
                var facestring = (dom_selected.length == 1) ? "selected face" : dom_selected.length + " selected faces";
                new Dialog("dialog-faces-delete","Delete faces",'Do you want to delete the '+ facestring + '?', function() {
                    RemoteClient.cmd('delete_faces',{images:selected});
                    GUI.loading.show();
                    return true;
                }, function() {
                    if (dom_selected.length == 1)
                        dom_selected.trigger('unselect');
                    return true;
                },true);
            }
        }
        
        addKeyDownEvents() {
            var facetagger = this;
            $(document).on('keydown',function(evt) {
                if (!Overlay.any_visible) {
                    var key = (evt.which || evt.keyCode);
                    if(key == 46) {//del
                        facetagger.delete_selected();
                        evt.preventDefault();
                    }
                }
            });
        }

        static Face = class extends Page.ImageList.Image{
            constructor (facetagger,img_index,img_src,face_index,face_src,name,ignored,force_reload=false) {
                super(facetagger,img_index,face_src,img_src,force_reload);
                this.face_index = face_index;
                this.face_src = face_src;
                this.name = name;
                this.ignored = ignored;
                this.create();
            }

            create() {
                var face = this;
                face.elem.attr('faceindex',face.face_index);
                face.elem.on('focused',function() {
                    if (face.is_last) {
                        face.imagelist.load_next(10,true);
                    }
                })
                face.input = $('<input />', {
                                type: "text",
                                placeholder: "type in name",
                                value: face.name})
                            .appendTo($('<div>').appendTo(face.elem))
                            .attr('autocomplete','off')
                            .autocomplete({ source: face.imagelist.known_names, minLength: 1, autoFocus: false, select: function(event, ui) { }});

                face.btn_ok = $('<input />', {type: 'image', src: '/web/greentick.png', alt: 'Ok', title: 'Apply name'});
                face.btn_ignore = $('<input />', {type: 'image', src: '/web/blackignore.png', alt: 'Ignore', title: 'Ignore'}).toggle(!face.ignored);
                face.btn_delete = $('<input />', {type: 'image', src: '/web/redcross.png', alt: 'Delete', title: 'Delete'});
                $('<div>').appendTo(face.elem)
                    .append(face.btn_ok)
                    .append(face.btn_ignore)
                    .append(face.btn_delete);

                face._add_events();
            }
                
            _add_events() {
                var face = this;

                face.input.on('keydown',function(evt){
                    var key = (evt.which || evt.keyCode) ;
                    if(key == 13) {//enter
                        face.select();
                        face.imagelist.name_selected(face.elem.val());
                        evt.preventDefault();
                    }
                    evt.stopPropagation();
                });

                face.btn_ok.on('click',function(evt){
                    if (!evt.ctrlKey && !evt.shiftKey){
                        var name = face.input.val().trim();
                        if (name != '') {
                            face.select();
                            face.imagelist.name_selected(name);
                        }
                        evt.stopPropagation();
                    }
                });

                face.btn_ignore.on('click',function(evt){
                    if (!evt.ctrlKey && !evt.shiftKey){
                        face.select();
                        face.imagelist.ignore_selected();
                        evt.stopPropagation();
                    }
                });

                face.btn_delete.on('click',function(evt){
                    if (!evt.ctrlKey && !evt.shiftKey){
                        face.select();
                        face.imagelist.delete_selected();
                        evt.stopPropagation();
                    }
                });
            }
        }
    }

    static Logs = class extends Page {

        constructor() {
            super('logs');
            this.menu.add_default();
            this.load();
        }

        load() {
            var logs = this;
            RemoteClient.cmd('load_logs',{},(data) => data.forEach((log)=>logs.add_entry(log)));
        }

        add_entry(data) {
            this.content.append(
                $('<span class="logentry"><span class="logdate">'+data[0]+'</span>: '+data[1]+'</span><br/>')
            );
        }

        addResponseHandler() {
            super.addResponseHandler();
            var logs = this;
            RemoteClient.add_callback('new_log_entry',function(data) {
                logs.add_entry(data);
            });
        }
    }

    static Setup = class extends Page {
        constructor() {
            super('setup');
            var setup = this;
            $.get( "/web/setup.html", function(data) {
                setup.content.append(data);
                setup.show()
            })
            .fail(function() {
                new Popup( "Failed to initalize setup, try again." );
            });
        }

        show() {
            var setup = this;
            this.step = "features";
            var apikey = Settings.create_gapi("gapi_key","apikey",Settings.get('valid_credentials'));
            var credentials = Settings.create_gapi("gapi_credentials","credentials",Settings.get('valid_credentials'));
            
            $('#setup').append(
                Html.table("Google API credentials").addClass('settings')
                    .append(Html.row("API key file",apikey))
                    .append(Html.row("Credentials file (*.json)",credentials)));
                
            var button = Settings.create_button('Continue',function() {
                switch (setup.step) {
                    case "features":
                        $('#setup .features').remove();
                        $('#setup .terms-of-use').show();
                        setup.step = "terms-of-use";
                        $(this).val('Agree');
                        break;
                    case "terms-of-use":
                        $('#setup .terms-of-use').remove();
                        $('#setup .settings, #setup .requirements').show();
                        setup.step = "credentials";
                        $(this).val('Save');
                        break;
                    case "credentials":
                        if (apikey.hasClass('valid') && credentials.hasClass('valid')){
                            Settings.set('valid_credentials',true);
                            Settings.save(() => GUI.load_page('settings'));
                        } else {
                            new Popup("Invalid GAPI credentials","You have to enter a valid API key file as well as a valid credentials file.");
                        }
                        break;
                }
            })
            setup.footer.left.append(button);
        }
    }

    static Settings = class extends Page {
        constructor() {
            super('settings');
            var settings = this;
            this.menu.add_default();
            this.content.append(
                Html.table("Path settings").addClass('settings')
                    .append(Html.row("Paths to scan",Settings.create_filelist("paths",5,true)))
                    .append(Html.row("Blacklist (regex)",Settings.create_regex("blacklist")))
                    .append(Html.row("Scan paths on startup",Settings.create_checkbox("scan_existing")))
                    .append(Html.row("Watch for new files",Settings.create_checkbox("scan_new")))
                ).append(
                Html.table("Default annotation settings").addClass('settings')
                    .append(Html.row("Vision Features",Settings.create_visionfeatures("vision_features")))
                    .append(Html.row('Reverse geocoding',Settings.create_checkbox("reverse_geocoding")))
                    .append(Html.row("Translate labels",Settings.create_language("translate")))
                    .append(Html.row('Replace labels',Settings.create_checkbox("replace_labels")))
                    .append(Html.row("Remove EXIF orientation",Settings.create_checkbox("rotate_images")))
                ).append(
                Html.table("Google API credentials").addClass('settings')
                    .append(Html.row("API key file",Settings.create_gapi("gapi_key","apikey",Settings.get('valid_credentials'))))
                    .append(Html.row("Credentials file (*.json)",Settings.create_gapi("gapi_credentials","credentials",Settings.get('valid_credentials'))))
                ).append(
                Html.table("Miscellaneous settings").addClass('settings')
                    .append(Html.row("Annotaion threads",Settings.create_number("num_threads",1,10,1)))
                    .append(Html.row("Synology NAS",Settings.create_checkbox("is_synology")))
                ).append(
                Html.table("GUI settings").addClass('settings')
                    .append(Html.row("Always hide menu",Settings.create_checkbox("always_hide_menu")))
                );
            this.btn_save = Settings.create_button('Save',() => settings.save()).prop("disabled",true).appendTo(this.footer.left);
            $(window).on('settings_changed',() => this.btn_save.prop("disabled",!Settings.changed));
        }

        save() {
            Settings.save();
            this.btn_save.prop("disabled",true);
        }
    }
}


class Menu {
    constructor() {
        var menu = this;
        this.elem = $('<div>',{id:'menu'}).append($('<div>'));
        this.button = $('<div>',{id:'menu_button'}).append($('<img />',{src: '/web/menubutton.svg'})).on('click', () => menu.toggle()).appendTo(this.elem);
        this.elem.append($('<div>',{id:'dummy'})).append($('<div>',{id:'version'}).html('gapi-annotator v0.1'));
        this.overlay = $('<div>',{"class":"menu-overlay overlay"}).appendTo('body').on('click',()=>menu.hide());

        if(window.matchMedia('(max-width: 1000px)').matches || Settings.get('always_hide_menu'))
            this.hide();
        else
            this.show();

        this.elem.prependTo('body');
    }

    add_default() {
        this.add_page('Facetagger');
        this.add_page('Duplicates');
        this.add_page('Annotation');
        this.add_page('Settings');
        this.add_page('Logs');
    }

    add_page(path) {
        path = path.toLowerCase();
        this.add_link(path.capitalize(),'/'+path).on('click',function(evt){
            evt.preventDefault();
            if (path != GUI.path) {
                GUI.load_page(path);
            }
        });
    }

    add_link(title,path) {
        return $('<div>',{"class":"entry"}).insertBefore(this.elem.find('#dummy'))
            .append($('<a>',{href:path})
                    .append(title));
    }

    show() {
        $('body').addClass('menu-visible');
    }

    hide() {
        $('body').removeClass('menu-visible');
    }

    toggle() {
        if ($('body').hasClass("menu-visible"))
            this.hide();
        else
            this.show();
    }
}

class Header {
    constructor(id){
        this.id = id;
        this.elem = $('<div>',{id:id}).appendTo('body')
        this.left = $('<div>',{id:id+'-left'}).appendTo(this.elem);
        this.right = $('<div>',{id:id+'-right'}).appendTo(this.elem);
    }
}