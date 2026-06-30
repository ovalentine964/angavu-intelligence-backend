const jwt = require('jsonwebtoken');
const JWT_SECRET = process.env.JWT_SECRET || 'msaidizi-secret-key-change-in-production';

function authenticate(req, res, next) {
    try {
        const authHeader = req.headers.authorization;
        if (!authHeader) return res.status(401).json({ status: 'error', message: 'Authorization header required' });
        const token = authHeader.startsWith('Bearer ') ? authHeader.slice(7) : authHeader;
        if (!token) return res.status(401).json({ status: 'error', message: 'Token required' });
        const decoded = jwt.verify(token, JWT_SECRET);
        req.user = { userId: decoded.userId, phone: decoded.phone, name: decoded.name };
        next();
    } catch (error) {
        if (error.name === 'TokenExpiredError') return res.status(401).json({ status: 'error', message: 'Token expired' });
        if (error.name === 'JsonWebTokenError') return res.status(401).json({ status: 'error', message: 'Invalid token' });
        console.error('Auth error:', error);
        return res.status(500).json({ status: 'error', message: 'Authentication error' });
    }
}

function optionalAuth(req, res, next) {
    try {
        const authHeader = req.headers.authorization;
        if (!authHeader) { req.user = null; return next(); }
        const token = authHeader.startsWith('Bearer ') ? authHeader.slice(7) : authHeader;
        if (!token) { req.user = null; return next(); }
        const decoded = jwt.verify(token, JWT_SECRET);
        req.user = { userId: decoded.userId, phone: decoded.phone, name: decoded.name };
        next();
    } catch (error) { req.user = null; next(); }
}

function generateToken(user) {
    return jwt.sign({ userId: user.userId, phone: user.phone, name: user.name }, JWT_SECRET, { expiresIn: '30d' });
}

module.exports = { authenticate, optionalAuth, generateToken, JWT_SECRET };
