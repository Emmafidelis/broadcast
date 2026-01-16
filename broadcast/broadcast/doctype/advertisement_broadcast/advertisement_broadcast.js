frappe.ui.form.on('Advertisement Broadcast', {
    refresh: function(frm) {
        // Update payment status
        if (frm.doc.docstatus === 1 && frm.doc.sales_invoice) {
            frm.call('update_payment_status').then(() => {
                frm.refresh_field('payment_status');
            });
        }

        // Show payment status indicator
        if (frm.doc.payment_status) {
            let indicator = 'orange';
            if (frm.doc.payment_status === 'Paid') indicator = 'green';
            else if (frm.doc.payment_status === 'Overdue') indicator = 'red';
            
            frm.dashboard.add_indicator(__('Payment: {0}', [frm.doc.payment_status]), indicator);
        }

        // Show autoplay status
        if (frm.doc.autoplay_enabled && frm.doc.audio_file) {
            frm.add_custom_button(__('Check Autoplay Status'), function() {
                frm.call('check_payment_and_autoplay').then(r => {
                    if (r.message.allowed) {
                        frappe.msgprint({
                            title: __('Autoplay Ready'),
                            indicator: 'green',
                            message: __('This advertisement is ready for autoplay at scheduled time.')
                        });
                    } else {
                        frappe.msgprint({
                            title: __('Autoplay Blocked'),
                            indicator: 'red',
                            message: __('Reason: {0}', [r.message.reason])
                        });
                    }
                });
            }, __('Actions'));
        }

        if (frm.doc.status === 'Scheduled') {
            frm.add_custom_button(__('Log Broadcast'), function() {
                frappe.call({
                    method: 'broadcast.broadcast.api.manual_broadcast_log',
                    args: {
                        advertisement_id: frm.doc.name,
                        actual_datetime: frappe.datetime.now_datetime(),
                        actual_duration: frm.doc.duration_seconds || 30,
                        notes: 'Logged via custom button'
                    },
                    freeze: true,
                    freeze_message: __('Logging broadcast...'),
                    callback: function(r) {
                        if (r.message && r.message.status === 'success') {
                            frappe.show_alert({
                                message: __('Broadcast logged successfully'),
                                indicator: 'green'
                            });
                            frm.reload_doc();
                        } else {
                            frappe.show_alert({
                                message: r.message ? r.message.message : __('Error logging broadcast'),
                                indicator: 'red'
                            });
                        }
                    }
                });
            }, __('Actions'));
        }

        // Create Sales Order button
        if (frm.doc.docstatus === 1 && !frm.doc.sales_order) {
            frm.add_custom_button(__('Create Sales Order'), function() {
                frm.call('create_sales_order').then(() => {
                    frappe.show_alert({message: __('Sales Order created'), indicator: 'green'});
                    frm.reload_doc();
                });
            }, __('Create'));
        }

        // Create Invoice button (only if paid)
        if (frm.doc.docstatus === 1 && frm.doc.status === 'Aired' && !frm.doc.sales_invoice && frm.doc.sales_order) {
            frm.add_custom_button(__('Create Invoice'), function() {
                frm.call('create_sales_invoice').then(() => {
                    frappe.show_alert({message: __('Invoice created'), indicator: 'green'});
                    frm.reload_doc();
                });
            }, __('Create'));
        }

        frm.add_custom_button(__('View Scheduled'), function() {
            frappe.call({
                method: 'broadcast.broadcast.api.get_scheduled_broadcasts',
                args: {hours_ahead: 24},
                freeze: true,
                callback: function(r) {
                    if (r.message && r.message.status === 'success') {
                        show_scheduled_broadcasts_dialog(r.message.broadcasts);
                    }
                }
            });
        }, __('Actions'));
    },

    audio_file: function(frm) {
        if (frm.doc.audio_file && !frm.doc.autoplay_enabled) {
            frappe.msgprint(__('Media file uploaded. Enable autoplay to broadcast automatically.'));
        }
    },

    autoplay_enabled: function(frm) {
        if (frm.doc.autoplay_enabled && !frm.doc.audio_file) {
            frappe.msgprint(__('Please upload a media file to enable autoplay.'));
        }
    },

    status: function(frm) {
        if (frm.doc.status === 'Aired' && frm.doc.auto_generate_invoice && !frm.doc.sales_invoice) {
            frm.call('create_sales_invoice').then(() => {
                frappe.show_alert({message: __('Invoice auto-generated'), indicator: 'green'});
                frm.reload_doc();
            });
        }
    }
});

function show_scheduled_broadcasts_dialog(broadcasts) {
    const dialog = new frappe.ui.Dialog({
        title: __('Scheduled Broadcasts'),
        size: 'large',
        fields: [{fieldtype: 'HTML', fieldname: 'broadcasts_html'}]
    });

    dialog.set_primary_action(__('Close'), () => dialog.hide());

    const data = Array.isArray(broadcasts) ? broadcasts : [];
    const wrapper = dialog.fields_dict.broadcasts_html.$wrapper;

    if (!data.length) {
        wrapper.html(`<div class="text-muted text-center py-4">${__('No scheduled broadcasts.')}</div>`);
        dialog.show();
        return;
    }

    const rows = data.map((b) => {
        let autoplay_badge = '';
        if (b.autoplay_allowed) {
            autoplay_badge = '<span class="badge badge-success">Autoplay Ready</span>';
        } else if (b.autoplay_enabled) {
            autoplay_badge = '<span class="badge badge-warning">Blocked</span>';
        }

        return `
            <tr>
                <td><a href="/app/advertisement-broadcast/${b.name}" target="_blank">${b.advertisement_title}</a></td>
                <td>${b.customer}</td>
                <td>${b.scheduled_date} ${b.scheduled_time}</td>
                <td>${b.payment_status || 'Unpaid'}</td>
                <td>${autoplay_badge}</td>
            </tr>
        `;
    }).join('');

    wrapper.html(`
        <table class="table table-bordered">
            <thead>
                <tr>
                    <th>${__('Title')}</th>
                    <th>${__('Customer')}</th>
                    <th>${__('Scheduled')}</th>
                    <th>${__('Payment')}</th>
                    <th>${__('Autoplay')}</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
    `);

    dialog.show();
}
