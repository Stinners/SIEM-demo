
const makeEvents = (events, eventContainer) => {
    if (events) {
        events.forEach(event => {
            let newNode = document.createElement("div");
            newNode.innerHTML = event;
            eventContainer.appendChild(newNode);
        });
    }
}

function sleep(seconds) {
    return new Promise(_ => setTimeout(_, seconds * 1000));
}

const poll = async (eventContainer) => {
    fetch("/poll/poll")
        .then(response => response.json())
        .then(data => data.events)
        .then((events) => makeEvents(events, eventContainer));
}

const poller = async (secondsDelay, eventContainer) => {
    let page = "/event";
    while (window.location.pathname == page) {
        await poll(eventContainer);
        await sleep(secondsDelay);
    }
}