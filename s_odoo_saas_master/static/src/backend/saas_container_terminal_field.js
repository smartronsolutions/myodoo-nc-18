/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onPatched, useRef, useState } from "@odoo/owl";

export class SaasContainerTerminal extends Component {
    static template = "s_odoo_saas_master.SaasContainerTerminal";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.outputElement = useRef("terminalOutput");
        this.inputElement = useRef("terminalInput");
        this.history = [];
        this.historyIndex = 0;
        const recordData = this.props.record.data;
        const isPostgres = recordData.terminal_type === "psql";
        const database = recordData.current_database || "postgres";
        this.state = useState({
            output: recordData[this.props.name] || (
                isPostgres
                    ? `Connected to PostgreSQL database: ${database}\nEnter SQL or psql commands and press Enter.`
                    : "Connected to the Odoo Docker container.\nEnter a shell command and press Enter."
            ),
            command: "",
            prompt: isPostgres ? `${database}=>` : "$",
            running: false,
            lastExitCode: 0,
        });

        onMounted(() => {
            this._scrollAndFocus();
        });
        onPatched(() => this._scrollToBottom());
    }

    _scrollToBottom() {
        if (this.outputElement.el) {
            this.outputElement.el.scrollTop = this.outputElement.el.scrollHeight;
        }
    }

    _scrollAndFocus() {
        this._scrollToBottom();
        if (this.inputElement.el) {
            this.inputElement.el.focus();
        }
    }

    async execute() {
        const command = this.state.command.trim();
        if (!command || this.state.running || !this.props.record.resId) {
            return;
        }
        if (command === "clear") {
            await this.clear();
            return;
        }

        this.history.push(command);
        this.historyIndex = this.history.length;
        this.state.command = "";
        this.state.running = true;
        const previousOutput = this.state.output;
        const pendingPrompt = `${this.state.prompt} ${command}`;
        this.state.output = `${previousOutput}\n\n${pendingPrompt}\nRunning...`;
        try {
            const result = await this.orm.call(
                this.props.record.resModel,
                "execute_terminal_command",
                [[this.props.record.resId], command]
            );
            this.state.output = `${previousOutput}\n\n${result.block}`;
            this.state.prompt = String(result.prompt || this.state.prompt).trim();
            this.state.lastExitCode = result.exit_code;
        } catch (error) {
            this.state.lastExitCode = 1;
            this.state.output = `${this.state.output}\n${error.message || "Command execution failed."}`;
        } finally {
            this.state.running = false;
            setTimeout(() => this._scrollAndFocus(), 0);
        }
    }

    async clear() {
        if (this.state.running || !this.props.record.resId) {
            return;
        }
        try {
            const result = await this.orm.call(
                this.props.record.resModel,
                "clear_terminal",
                [[this.props.record.resId]]
            );
            this.state.output = "";
            this.state.command = "";
            this.state.prompt = String(result.prompt || this.state.prompt).trim();
            this.state.lastExitCode = 0;
        } finally {
            setTimeout(() => this._scrollAndFocus(), 0);
        }
    }

    onKeydown(event) {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            this.execute();
        } else if (event.key === "ArrowUp") {
            event.preventDefault();
            if (this.historyIndex > 0) {
                this.historyIndex -= 1;
                this.state.command = this.history[this.historyIndex];
            }
        } else if (event.key === "ArrowDown") {
            event.preventDefault();
            if (this.historyIndex < this.history.length - 1) {
                this.historyIndex += 1;
                this.state.command = this.history[this.historyIndex];
            } else {
                this.historyIndex = this.history.length;
                this.state.command = "";
            }
        }
    }
}

registry.category("fields").add("saas_container_terminal", {
    component: SaasContainerTerminal,
});
