
const makeEvents = (events, eventContainer) => {
    if (events) {
        events.forEach(event => {
            let newNode = document.createElement("div");
            newNode.innerHTML = event;
            eventContainer.appendChild(newNode);
        });
    }
}

const poll = async (eventContainer) => {
    let response = await fetch("/poll/poll");
    let json = await response.json();

    if (json.poll == "not started") {
        await fetch("/poll/subscribe", {"method": "POST"});
    }

    let events = json.events;
    makeEvents(events, eventContainer);
}

const poller = async (eventContainer) => {
    let page = "/event";
    while (window.location.pathname == page) {
        await poll(eventContainer);
    }
}