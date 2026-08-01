/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onPatched, onWillUnmount, useRef, useState } from "@odoo/owl";

export class SaasLiveOdooLogs extends Component {
    static template = "s_odoo_saas_master.SaasLiveOdooLogs";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.logElement = useRef("logOutput");
        this.pollTimer = null;
        this.destroyed = false;
        this.lastSnapshot = null;
        this.state = useState({
            logs: "Connecting to the Odoo container...",
            refreshing: false,
            live: true,
            error: false,
            updatedAt: "",
        });

        onMounted(async () => {
            await this.refresh();
            this._schedulePoll();
        });
        onPatched(() => this._scrollToBottom());
        onWillUnmount(() => {
            this.destroyed = true;
            this._clearPoll();
        });
    }

    _clearPoll() {
        if (this.pollTimer) {
            clearTimeout(this.pollTimer);
            this.pollTimer = null;
        }
    }

    _schedulePoll() {
        this._clearPoll();
        if (this.state.live && !this.destroyed) {
            this.pollTimer = setTimeout(() => this._poll(), 2500);
        }
    }

    async _poll() {
        try {
            await this.refresh();
        } finally {
            this._schedulePoll();
        }
    }

    _scrollToBottom() {
        if (this.logElement.el) {
            this.logElement.el.scrollTop = this.logElement.el.scrollHeight;
        }
    }

    _mergeSnapshot(output) {
        const newLines = String(output || "").split("\n");
        if (this.lastSnapshot === null) {
            this.lastSnapshot = newLines;
            return newLines.join("\n");
        }

        let overlap = Math.min(this.lastSnapshot.length, newLines.length);
        while (overlap > 0) {
            const oldTail = this.lastSnapshot.slice(-overlap).join("\n");
            const newHead = newLines.slice(0, overlap).join("\n");
            if (oldTail === newHead) {
                break;
            }
            overlap -= 1;
        }
        this.lastSnapshot = newLines;
        const addedLines = newLines.slice(overlap);
        if (!addedLines.length) {
            return this.state.logs;
        }
        // Keep a useful live history without allowing a long-running dialog to
        // consume unbounded browser memory.
        const history = `${this.state.logs}\n${addedLines.join("\n")}`.split("\n");
        return history.slice(-5000).join("\n");
    }

    async refresh() {
        if (!this.props.record.resId || this.state.refreshing || this.destroyed) {
            return;
        }
        this.state.refreshing = true;
        try {
            const result = await this.orm.call(
                this.props.record.resModel,
                "get_live_logs",
                [[this.props.record.resId]]
            );
            if (!this.destroyed) {
                this.state.error = Boolean(result.exit_code);
                if (result.exit_code) {
                    this.state.logs = result.output;
                    this.lastSnapshot = null;
                } else {
                    this.state.logs = this._mergeSnapshot(result.output);
                }
                this.state.updatedAt = result.updated_at || "";
            }
        } catch (error) {
            if (!this.destroyed) {
                this.state.error = true;
                this.state.logs = error.message || "Unable to load Odoo logs.";
            }
        } finally {
            if (!this.destroyed) {
                this.state.refreshing = false;
            }
        }
    }

    async onRefreshClick() {
        this._clearPoll();
        await this.refresh();
        this._schedulePoll();
    }

    onToggleLive() {
        this.state.live = !this.state.live;
        this._schedulePoll();
    }
}

registry.category("fields").add("saas_live_odoo_logs", {
    component: SaasLiveOdooLogs,
});
