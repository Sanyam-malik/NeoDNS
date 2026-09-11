// Random gradient background logic
function getRandomColor() {
    return '#' + Math.floor(Math.random() * 16777215).toString(16).padStart(6, '0');
}

function setRandomGradient() {
    const color1 = getRandomColor();
    const color2 = getRandomColor();
    const color3 = getRandomColor();
    const color4 = getRandomColor();
    document.body.style.background = `linear-gradient(-45deg, ${color1}, ${color2}, ${color3}, ${color4})`;
}

setRandomGradient(); // Initial call
setInterval(setRandomGradient, 15000); // Change every 15s

// Spinner methods
function showSpinner() {
    document.getElementById('spinner-overlay').classList.remove('d-none');
}

function hideSpinner() {
    document.getElementById('spinner-overlay').classList.add('d-none');
}

// Load configuration
async function loadConfig() {
    showSpinner();
    try {
        const res = await fetch("/api/config");
        const data = await res.json();
        updateUI(data);
    } catch (error) {
        console.error("Error loading config:", error);
    } finally {
        hideSpinner();
    }
}

// Perform dig
function performDig() {
    const domain = document.getElementById("digDomainInput").value.trim();
    const outputElement = document.getElementById("digOutput");

    if (!domain) {
        outputElement.textContent = "Please enter a domain.";
        outputElement.classList.add("d-none");
        return;
    }

    outputElement.classList.add("d-none");
    showSpinner();

    fetch("/api/dig", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain })
    })
    .then(response => response.json())
    .then(data => {
        outputElement.classList.remove("d-none");
        outputElement.textContent = data.output || data.error || "No output received.";
    })
    .catch(error => {
        outputElement.textContent = `Error: ${error}`;
    })
    .finally(() => {
        hideSpinner();
    });
}

// Update UI
function updateUI(config) {
    const resolvers = config.resolvers || [];
    const resolverList = document.getElementById("resolver-list");
    resolverList.innerHTML = "";
    resolvers.forEach((ip) => {
        const li = document.createElement("li");
        li.className = "list-group-item d-flex justify-content-between align-items-center";
        li.textContent = ip;
        const btn = document.createElement("button");
        btn.className = "btn btn-sm btn-danger";
        btn.textContent = "Remove";
        btn.onclick = () => removeResolver(ip);
        li.appendChild(btn);
        resolverList.appendChild(li);
    });

    const domains = config.domains || {};
    const accordion = document.getElementById("domainAccordion");
    accordion.innerHTML = "";

    let i = 0;
    for (const domain in domains) {
        const domainData = domains[domain];
        const domainIp = domainData.ip || "";
        const subdomains = domainData.subdomains || {};
        const collapseId = `collapse${i}`;

        const item = document.createElement("div");
        item.className = "accordion-item";
        item.innerHTML = `
        <h2 class="accordion-header">
            <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#${collapseId}">
                ${domain} (${domainIp})
            </button>
        </h2>
        <div id="${collapseId}" class="accordion-collapse collapse" data-bs-parent="#domainAccordion">
            <div class="accordion-body">
                <table class="table table-bordered subdomain-table mb-3">
                    <thead>
                        <tr><th>Subdomain</th><th>IP/Host</th><th>Action</th></tr>
                    </thead>
                    <tbody id="subdomain-list-${i}"></tbody>
                </table>
                <div id="subdomain-alert-${i}" class="alert alert-warning d-none" role="alert">
                    This subdomain already exists. Please remove it first before adding a new one.
                </div>
                <div class="row mb-2">
                    <div class="col">
                        <input type="text" class="form-control" id="new-sub-${i}" placeholder="Subdomain (e.g. acme or acme.example.com)">
                    </div>
                    <div class="col">
                        <input type="text" class="form-control" id="new-ip-${i}" placeholder="IP/Host (e.g. 192.168.1.2)">
                    </div>
                    <div class="col-auto">
                        <button class="btn btn-primary" onclick="addSubdomain('${domain}', ${i})">Add Subdomain</button>
                    </div>
                </div>
                <div class="d-flex justify-content-between mt-3">
                    <button class="btn btn-sm btn-danger" onclick="deleteDomain('${domain}')">Remove Domain</button>
                </div>
            </div>
        </div>
    `;
        accordion.appendChild(item);

        const subList = item.querySelector(`#subdomain-list-${i}`);
        for (const sub in subdomains) {
            const row = document.createElement("tr");
            row.innerHTML = `
            <td>${sub}.${domain}</td>
            <td>
                <input
                type="text"
                class="form-control"
                value="${subdomains[sub]}"
                onfocus="this.dataset.prevValue = this.value"
                onchange="handleSubdomainChange(this, '${domain}', '${sub}')">
            </td>
            <td><button class="btn btn-sm btn-outline-danger" onclick="removeSubdomain('${domain}', '${sub}')">Remove</button></td>
        `;
            subList.appendChild(row);
        }
        i++;
    }
}

// Add resolver
async function addResolver() {
    showSpinner();
    try {
        const ip = document.getElementById("new-resolver").value;
        const alertBox = document.getElementById("resolver-alert");
        if (!ip) return;

        const res = await fetch("/api/config");
        const config = await res.json();
        if (config.resolvers.includes(ip)) {
            alertBox.classList.remove("d-none");
            setTimeout(() => alertBox.classList.add("d-none"), 2000);
            return;
        } else {
            alertBox.classList.add("d-none");
        }

        await fetch("/api/resolver", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ip }),
        });

        await loadConfig();
    } catch (error) {
        console.error("Error adding resolver:", error);
    } finally {
        hideSpinner();
    }
}

// Remove resolver
async function removeResolver(ip) {
    showSpinner();
    try {
        await fetch("/api/resolver", {
            method: "DELETE",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ip }),
        });
        await loadConfig();
    } catch (error) {
        console.error("Error removing resolver:", error);
    } finally {
        hideSpinner();
    }
}

function handleSubdomainChange(input, domain, subdomain) {
    const newValue = input.value.trim();
    const prevValue = input.dataset.prevValue;

    if (newValue === "") {
        input.value = prevValue; // Revert
        return;
    }

    updateSubdomain(domain, subdomain, newValue);
}


// Add or update domain
async function addOrUpdateDomain() {
    showSpinner();
    try {
        const domain = document.getElementById("domain-name").value.trim();
        const ip = document.getElementById("domain-ip").value.trim();
        const alertBox = document.getElementById("domain-alert");
        if (!domain || !ip) return;

        const res = await fetch("/api/config");
        const config = await res.json();
        if (config.domains[domain]) {
            alertBox.classList.remove("d-none");
            setTimeout(() => alertBox.classList.add("d-none"), 2000);
            return;
        } else {
            alertBox.classList.add("d-none");
        }

        await fetch("/api/domain", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ domain, ip, subdomains: {} }),
        });

        await loadConfig();
    } catch (error) {
        console.error("Error adding domain:", error);
    } finally {
        hideSpinner();
    }
}

// Delete domain
async function deleteDomain(domain) {
    showSpinner();
    try {
        await fetch("/api/domain", {
            method: "DELETE",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ domain }),
        });
        await loadConfig();
    } catch (error) {
        console.error("Error deleting domain:", error);
    } finally {
        hideSpinner();
    }
}

// Add subdomain
async function addSubdomain(domain, i) {
    showSpinner();
    try {
        let subInput = document.getElementById(`new-sub-${i}`).value.trim();
        const ip = document.getElementById(`new-ip-${i}`).value.trim();
        const alertBox = document.getElementById(`subdomain-alert-${i}`);

        if (!subInput || !ip) return;

        if (subInput.includes(".")) {
            if (!subInput.endsWith(`.${domain}`)) {
                alertBox.textContent = `Subdomain must belong to the "${domain}" domain.`;
                alertBox.classList.remove("d-none");
                setTimeout(() => alertBox.classList.add("d-none"), 2500);
                return;
            }
            subInput = subInput.slice(0, subInput.length - domain.length - 1);
        }

        const res = await fetch("/api/config");
        const config = await res.json();
        const subdomains = config.domains[domain]?.subdomains || {};
        if (subdomains[subInput]) {
            alertBox.textContent = `This subdomain already exists. Please remove it first before adding a new one.`;
            alertBox.classList.remove("d-none");
            setTimeout(() => alertBox.classList.add("d-none"), 2500);
            return;
        }

        alertBox.classList.add("d-none");

        await fetch("/api/subdomain", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ domain, subdomain: subInput, ip }),
        });

        await loadConfig();
    } catch (error) {
        console.error("Error adding subdomain:", error);
    } finally {
        hideSpinner();
    }
}

// Remove subdomain
async function removeSubdomain(domain, subdomain) {
    showSpinner();
    try {
        await fetch("/api/subdomain", {
            method: "DELETE",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ domain, subdomain }),
        });
        await loadConfig();
    } catch (error) {
        console.error("Error removing subdomain:", error);
    } finally {
        hideSpinner();
    }
}

// Update subdomain
async function updateSubdomain(domain, subdomain, ip) {
    showSpinner();
    try {
        await fetch("/api/subdomain", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ domain, subdomain, ip }),
        });
    } catch (error) {
        console.error("Error updating subdomain:", error);
    } finally {
        hideSpinner();
    }
}

// Initial load
loadConfig();
