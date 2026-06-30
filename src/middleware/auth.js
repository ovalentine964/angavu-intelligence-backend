/**
 * Authentication Middleware
 * 
 * Handles JWT token verification for protected routes.
 */

const jwt = require('jsonwebtoken');

const JWT_SECRET = process.env.JWT_SECRET || 'msaidizi-secret-key-change-in-production';

/**
 * Authenticate requests using JWT token.
 * 
 * Expects: Authorization: Bearer <token>
 */
function authenticate(req, res, next) {
    try {
        const authHeader = req.headers.authorization;

        if (!authHeader) {
            return res.status(401).json({
                status: 'error',
                message: 'Authorization header required'
            });
        }

        const token = authHeader.startsWith('Bearer ')
            ? authHeader.slice(7)
            : authHeader;

        if (!token) {
            return res.status(401).json({
                status: 'error',
                message: 'Token required'
            });
        }

        // Verify token
        const decoded = jwt.verify(token, JWT_SECRET);

        // Attach user info to request
        req.user = {
            userId: decoded.userId,
            phone: decoded.phone,
            name: decoded.name
        };

        next();

    } catch (error) {
        if (error.name === 'TokenExpiredError') {
            return res.status(401).json({
                status: 'error',
                message: 'Token expired'
            });
        }

        if (error.name === 'JsonWebTokenError') {
            return res.status(401).json({
                status: 'error',
                message: 'Invalid token'
            });
        }

        console.error('Auth middleware error:', error);
        return res.status(500).json({
            status: 'error',
            message: 'Authentication error'
        });
    }
}

/**
 * Optional authentication — doesn't fail if no token provided.
 * Useful for routes that work with or without auth.
 */
function optionalAuth(req, res, next) {
    try {
        const authHeader = req.headers.authorization;

        if (!authHeader) {
            req.user = null;
            return next();
        }

        const token = authHeader.startsWith('Bearer ')
            ? authHeader.slice(7)
            : authHeader;

        if (!token) {
            req.user = null;
            return next();
        }

        const decoded = jwt.verify(token, JWT_SECRET);
        req.user = {
            userId: decoded.userId,
            phone: decoded.phone,
            name: decoded.name
        };

        next();

    } catch (error) {
        // Don't fail, just set user to null
        req.user = null;
        next();
    }
}

/**
 * Generate a JWT token for a user.
 */
function generateToken(user) {
    return jwt.sign(
        {
            userId: user.userId,
            phone: user.phone,
            name: user.name
        },
        JWT_SECRET,
        { expiresIn: '30d' }
    );
}

module.exports = {
    authenticate,
    optionalAuth,
    generateToken,
    JWT_SECRET
};
