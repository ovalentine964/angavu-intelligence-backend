const PhoneValidator = require('../utils/PhoneValidator');

describe('PhoneValidator', () => {
    describe('validate', () => {
        test('valid local Safaricom number', () => {
            const result = PhoneValidator.validate('0712345678');
            expect(result.valid).toBe(true);
            expect(result.normalized).toBe('+254712345678');
            expect(result.carrier).toBe('SAFARICOM');
        });

        test('valid local Airtel number', () => {
            const result = PhoneValidator.validate('0112345678');
            expect(result.valid).toBe(true);
            expect(result.normalized).toBe('+254112345678');
            expect(result.carrier).toBe('AIRTEL');
        });

        test('valid international with plus', () => {
            const result = PhoneValidator.validate('+254712345678');
            expect(result.valid).toBe(true);
            expect(result.normalized).toBe('+254712345678');
        });

        test('valid international without plus', () => {
            const result = PhoneValidator.validate('254712345678');
            expect(result.valid).toBe(true);
            expect(result.normalized).toBe('+254712345678');
        });

        test('valid bare 9-digit number', () => {
            const result = PhoneValidator.validate('712345678');
            expect(result.valid).toBe(true);
            expect(result.normalized).toBe('+254712345678');
        });

        test('valid with spaces', () => {
            const result = PhoneValidator.validate('0712 345 678');
            expect(result.valid).toBe(true);
            expect(result.normalized).toBe('+254712345678');
        });

        test('valid with dashes', () => {
            const result = PhoneValidator.validate('0712-345-678');
            expect(result.valid).toBe(true);
            expect(result.normalized).toBe('+254712345678');
        });

        test('empty input', () => {
            const result = PhoneValidator.validate('');
            expect(result.valid).toBe(false);
            expect(result.error).toBe('Namba ya simu haijawekwa.');
        });

        test('null input', () => {
            const result = PhoneValidator.validate(null);
            expect(result.valid).toBe(false);
        });

        test('non-numeric input', () => {
            const result = PhoneValidator.validate('abc123');
            expect(result.valid).toBe(false);
        });

        test('too short number', () => {
            const result = PhoneValidator.validate('071234');
            expect(result.valid).toBe(false);
        });

        test('wrong prefix', () => {
            const result = PhoneValidator.validate('0512345678');
            expect(result.valid).toBe(false);
        });
    });

    describe('isValid', () => {
        test('returns true for valid number', () => {
            expect(PhoneValidator.isValid('0712345678')).toBe(true);
        });

        test('returns false for invalid number', () => {
            expect(PhoneValidator.isValid('123')).toBe(false);
        });
    });

    describe('detectCarrier', () => {
        test('detects Safaricom', () => {
            expect(PhoneValidator.detectCarrier('+254712345678')).toBe('SAFARICOM');
        });

        test('detects Airtel', () => {
            expect(PhoneValidator.detectCarrier('+254733123456')).toBe('AIRTEL');
        });

        test('detects Telkom', () => {
            expect(PhoneValidator.detectCarrier('+254201234567')).toBe('TELKOM');
        });
    });

    describe('formatForDisplay', () => {
        test('formats local number', () => {
            expect(PhoneValidator.formatForDisplay('0712345678')).toBe('0712 345 678');
        });

        test('formats international number', () => {
            expect(PhoneValidator.formatForDisplay('+254712345678')).toBe('0712 345 678');
        });
    });

    describe('toDigits', () => {
        test('extracts digits from local', () => {
            expect(PhoneValidator.toDigits('0712345678')).toBe('254712345678');
        });

        test('returns null for invalid', () => {
            expect(PhoneValidator.toDigits('123')).toBeNull();
        });
    });
});
