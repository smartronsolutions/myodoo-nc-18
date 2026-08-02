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
        this.cursor = 0;
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
            this.pollTimer = setTimeout(() => this._poll(), 1500);
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

    _appendLogs(output) {
        if (!output) {
            return;
        }
        const separator = this.state.logs ? "\n" : "";
        const history = `${this.state.logs}${separator}${output}`.split("\n");
        this.state.logs = history.slice(-5000).join("\n");
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
                [[this.props.record.resId], this.cursor]
            );
            if (!this.destroyed) {
                this.state.error = Boolean(result.exit_code);
                if (result.exit_code) {
                    this.state.logs = result.output;
                    this.cursor = 0;
                } else if (!this.cursor || result.reset) {
                    this.state.logs = result.output || "";
                } else {
                    this._appendLogs(result.output);
                }
                this.cursor = Number(result.cursor || 0);
                this.state.updatedAt = result.updated_at || "";
            }
        } catch (error) {
            if (!this.destroyed) {
                this.state.error = true;
                this.state.logs = error?.data?.message ||
                    error?.cause?.data?.message ||
                    error?.message ||
                    "Unable to load Odoo logs.";
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
