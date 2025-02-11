// get DOM elements
var iceConnectionLog = document.getElementById('ice-connection-state'),
    iceGatheringLog = document.getElementById('ice-gathering-state'),
    signalingLog = document.getElementById('signaling-state');



function goToPage(pageNumber) {
    // Hide all pages
    var pages = document.querySelectorAll('.page');
    pages.forEach(function (page) {
        page.style.display = 'none';
    });

    // Display the selected page
    var selectedPage = document.getElementById('page' + pageNumber);
    if (selectedPage) {
        selectedPage.style.display = 'block';
    }
}

function closeTab() {
    // Check for ReactNativeWebView
    if (window.ReactNativeWebView) {
        window.ReactNativeWebView.postMessage('closeThisWindow');
    } else {
        console.warn("ReactNativeWebView not found.");
    }
}



// peer connection
var pc = null;
var pool_interval = null;

function createPeerConnection() {
    var config = {
        sdpSemantics: 'unified-plan'
    };

    if (document.getElementById('use-stun').checked) {
        config.iceServers = [{ urls: ['stun:stun.l.google.com:19302'] }];
    }

    pc = new RTCPeerConnection(config);

    // register some listeners to help debugging
    pc.addEventListener('icegatheringstatechange', function () {
        iceGatheringLog.textContent += ' -> ' + pc.iceGatheringState;
    }, false);
    iceGatheringLog.textContent = pc.iceGatheringState;

    pc.addEventListener('iceconnectionstatechange', function () {
        iceConnectionLog.textContent += ' -> ' + pc.iceConnectionState;
    }, false);
    iceConnectionLog.textContent = pc.iceConnectionState;

    pc.addEventListener('signalingstatechange', function () {
        signalingLog.textContent += ' -> ' + pc.signalingState;
    }, false);
    signalingLog.textContent = pc.signalingState;

    // connect audio / video
    pc.addEventListener('track', function (evt) {
        if (evt.track.kind == 'video') {
            document.getElementById('video').srcObject = evt.streams[0];
            const urlParams = new URLSearchParams(window.location.search);
            const token = urlParams.get('token');
            pool_interval = setInterval(() => {
                fetch(`/get_gestures_requester_process_status?token=${token}`, {
                    method: "GET",
                    headers: {
                        "Content-Type": "application/json"
                    }
                })
                    .then(response => response.json())
                    .then(data => {
                        // Handle the response data here
                        if (data.status == 3){ //DONE
                            clearPool();
                            goToPage(4);
                            setTimeout(()=>{
                                stop(); 
                                setTimeout(() => {
                                    closeTab();
                                }, 2000);
                            }, 1000)
                        } else if (data.status == 4) { //Failure
                            clearPool();
                            goToPage(5);
                            errorLog = document.getElementById("errorLog");
                            errorLog.innerHTML = data.log.map(line => `&bull; ${line}`).join('<br>');
                        }
                        //console.log(data);
                    })
                    .catch(error => {
                        // Handle any errors that occurred during the fetch request
                        console.error("Error:", error);
                    });
            }, 3000);
            goToPage(3);
        }
    });
    //else
        //document.getElementById('audio').srcObject = evt.streams[0];
    

    return pc;
}

function negotiate() {
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get('token');
    const rd = urlParams.get('rd');
    const d = urlParams.get('d');
    const q = urlParams.get('q');
    const lang = urlParams.get('lang');

    return pc.createOffer().then(function (offer) {
        console.log("Create Offer:", offer);
        return pc.setLocalDescription(offer);
    }).then(function () {
        // wait for ICE gathering to complete
        console.log("Wating");
        return new Promise(function (resolve) {
            if (pc.iceGatheringState === 'complete') {
                console.log("ICE gathering to complete");
                resolve();
            } else {
                function checkState() {
                    console.log("checkState");
                    if (pc.iceGatheringState === 'complete') {
                        pc.removeEventListener('icegatheringstatechange', checkState);
                        resolve();
                    }
                }
                pc.addEventListener('icegatheringstatechange', checkState);
            }
        });
    }).then(function () {
        var offer = pc.localDescription;
        var codec;


        //codec = document.getElementById('audio-codec').value;
        //if (codec !== 'default') {
        //    offer.sdp = sdpFilterCodec('audio', codec, offer.sdp);
        //}

        codec = document.getElementById('video-codec').value;
        if (codec !== 'default') {
            offer.sdp = sdpFilterCodec('video', codec, offer.sdp);
        }

        document.getElementById('offer-sdp').textContent = offer.sdp;
        console.log("Fetch to /offer", offer);
        let bodyData = {
            sdp: offer.sdp,
            type: offer.type,
            token: token
        }
        if (rd !== null) {
            bodyData.rd = rd;
        }
        if (d !== null) {
            bodyData.d = d;
        }
        if (q !== null) {
            bodyData.q = q;
        }
        if (lang !== null) {
            bodyData.lang = lang;
        }
        return fetch('/offer', {
            body: JSON.stringify(bodyData),
            headers: {
                'Content-Type': 'application/json'
            },
            method: 'POST'
        });
    }).then(function (response) {
        console.log("Fetch Response:", response);
        return response.json();
    }).then(function (answer) {
        console.log("Fetch Response, Answer:", answer)
        document.getElementById('answer-sdp').textContent = answer.sdp;
        return pc.setRemoteDescription(answer);
    }).catch(function (e) {
        alert(e);
    });
}

function clearPool() {
    if (pool_interval !== null) {
        clearInterval(pool_interval);
    }  
}

function start() {
    //document.getElementById('start').style.display = 'none';

    clearPool();
    pc = createPeerConnection();

    var time_start = null;

    function current_stamp() {
        if (time_start === null) {
            time_start = new Date().getTime();
            return 0;
        } else {
            return new Date().getTime() - time_start;
        }
    }

    var constraints = {
        audio: false,
        video: false
    };

    if (document.getElementById('use-video').checked) {
        var resolution = document.getElementById('video-resolution').value;
        if (resolution) {
            resolution = resolution.split('x');
            constraints.video = {
                width: parseInt(resolution[0], 0),
                height: parseInt(resolution[1], 0)
            };
        } else {
            constraints.video = true;
        }
    }

    if (constraints.video) {
        //if (constraints.video) {
        //    document.getElementById('media').style.display = 'block';
        //}
        navigator.mediaDevices.getUserMedia(constraints).then(function (stream) {
            //document.getElementById("video2").srcObject = stream
            stream.getTracks().forEach(function (track) {
                pc.addTrack(track, stream);
            });
            return negotiate();
        }, function (err) {
            alert('Could not acquire media: ' + err);
        });
    } else {
        negotiate();
    }

    //document.getElementById('stop').style.display = 'inline-block';
}

function stop() {
    pc.close();
}


function sdpFilterCodec(kind, codec, realSdp) {
    var allowed = []
    var rtxRegex = new RegExp('a=fmtp:(\\d+) apt=(\\d+)\r$');
    var codecRegex = new RegExp('a=rtpmap:([0-9]+) ' + escapeRegExp(codec))
    var videoRegex = new RegExp('(m=' + kind + ' .*?)( ([0-9]+))*\\s*$')

    var lines = realSdp.split('\n');

    var isKind = false;
    for (var i = 0; i < lines.length; i++) {
        if (lines[i].startsWith('m=' + kind + ' ')) {
            isKind = true;
        } else if (lines[i].startsWith('m=')) {
            isKind = false;
        }

        if (isKind) {
            var match = lines[i].match(codecRegex);
            if (match) {
                allowed.push(parseInt(match[1]));
            }

            match = lines[i].match(rtxRegex);
            if (match && allowed.includes(parseInt(match[2]))) {
                allowed.push(parseInt(match[1]));
            }
        }
    }

    var skipRegex = 'a=(fmtp|rtcp-fb|rtpmap):([0-9]+)';
    var sdp = '';

    isKind = false;
    for (var i = 0; i < lines.length; i++) {
        if (lines[i].startsWith('m=' + kind + ' ')) {
            isKind = true;
        } else if (lines[i].startsWith('m=')) {
            isKind = false;
        }

        if (isKind) {
            var skipMatch = lines[i].match(skipRegex);
            if (skipMatch && !allowed.includes(parseInt(skipMatch[2]))) {
                continue;
            } else if (lines[i].match(videoRegex)) {
                sdp += lines[i].replace(videoRegex, '$1 ' + allowed.join(' ')) + '\n';
            } else {
                sdp += lines[i] + '\n';
            }
        } else {
            sdp += lines[i] + '\n';
        }
    }

    return sdp;
}

function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); // $& means the whole matched string
}
