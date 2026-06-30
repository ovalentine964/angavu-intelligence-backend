class PhoneValidator {
    static PATTERNS = {
        LOCAL_10_DIGIT: /^0[17]\d{8}$/,
        LOCAL_10_DIGIT_02: /^020\d{7}$/,
        BARE_9_DIGIT: /^[17]\d{8}$/,
        INTL_WITH_PLUS: /^\+254[17]\d{8}$/,
        INTL_NO_PLUS: /^254[17]\d{8}$/
    };

    static CARRIERS = {
        SAFARICOM: ['0700', '0701', '0702', '0703', '0704', '0705', '0706', '0707', '0708', '0709', '0710', '0711', '0712', '0713', '0714', '0715', '0716', '0717', '0718', '0719', '0720', '0721', '0722', '0723', '0724', '0725', '0726', '0727', '0728', '0729', '0740', '0741', '0742', '0743', '0744', '0745', '0746', '0747', '0748', '0749', '0757', '0758', '0759', '0768', '0790', '0791', '0792', '0793', '0794', '0795', '0796', '0797', '0798', '0799'],
        AIRTEL: ['0730', '0731', '0732', '0733', '0734', '0735', '0736', '0737', '0738', '0739', '0750', '0751', '0752', '0753', '0754', '0755', '0756', '0100', '0101', '0102', '0103', '0104', '0105', '0106', '0107', '0108', '0109', '0110', '0111', '0112', '0113'],
        TELKOM: ['020']
    };

    static validate(raw) {
        if (!raw || typeof raw !== 'string') return { valid: false, normalized: null, error: 'Namba ya simu haijawekwa.', carrier: null };
        const cleaned = raw.replace(/[\s\-()]+/g, '').trim();
        if (cleaned.length === 0) return { valid: false, normalized: null, error: 'Namba ya simu haijawekwa.', carrier: null };
        if (!/^\+?\d+$/.test(cleaned)) return { valid: false, normalized: null, error: 'Namba ya simu ina herufi zisizotambulika.', carrier: null };

        const normalized = this.normalize(cleaned);
        if (!normalized) return { valid: false, normalized: null, error: 'Namba ya simu si sahihi. Tafadhali weka namba ya Kenya (mfano: 0712345678).', carrier: null };
        if (!/^\+254[17]\d{8}$/.test(normalized)) return { valid: false, normalized: null, error: 'Namba ya simu si sahihi. Hakikisha unaanzia 07XX au 01XX.', carrier: null };

        return { valid: true, normalized, error: null, carrier: this.detectCarrier(normalized) };
    }

    static isValid(raw) { return this.validate(raw).valid; }

    static normalize(cleaned) {
        if (this.PATTERNS.INTL_WITH_PLUS.test(cleaned)) return cleaned;
        if (this.PATTERNS.INTL_NO_PLUS.test(cleaned)) return `+${cleaned}`;
        if (this.PATTERNS.LOCAL_10_DIGIT.test(cleaned)) return `+254${cleaned.substring(1)}`;
        if (this.PATTERNS.LOCAL_10_DIGIT_02.test(cleaned)) return `+254${cleaned.substring(1)}`;
        if (this.PATTERNS.BARE_9_DIGIT.test(cleaned)) return `+254${cleaned}`;
        return null;
    }

    static detectCarrier(normalized) {
        const local = normalized.replace('+254', '0');
        for (const [carrier, prefixes] of Object.entries(this.CARRIERS)) {
            for (const prefix of prefixes) { if (local.startsWith(prefix)) return carrier; }
        }
        return 'UNKNOWN';
    }

    static formatForDisplay(raw) {
        const result = this.validate(raw);
        if (!result.valid) return raw;
        const local = result.normalized.replace('+254', '0');
        if (local.length === 10) return `${local.substring(0, 4)} ${local.substring(4, 7)} ${local.substring(7)}`;
        return raw;
    }

    static toDigits(raw) {
        const result = this.validate(raw);
        if (!result.valid) return null;
        return result.normalized.replace('+', '');
    }
}

module.exports = PhoneValidator;
