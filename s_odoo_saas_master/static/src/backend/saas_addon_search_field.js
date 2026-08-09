/** @odoo-module **/

import { registry } from "@web/core/registry";
import { debounce } from "@web/core/utils/timing";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, onWillUnmount } from "@odoo/owl";


export class SaasAddonSearchField extends Component {
    static template = "s_odoo_saas_master.SaasAddonSearchField";
    static props = {
        ...standardFieldProps,
        placeholder: { type: String, optional: true },
    };

    setup() {
        this.updateSearch = debounce(async (value) => {
            await this.props.record.update({ [this.props.name]: value });
        }, 250);
        onWillUnmount(() => this.updateSearch.cancel());
    }

    onInput(event) {
        this.updateSearch(event.target.value);
    }
}

registry.category("fields").add("saas_addon_search", {
    component: SaasAddonSearchField,
    supportedTypes: ["char"],
    extractProps: ({ placeholder }) => ({ placeholder }),
});
