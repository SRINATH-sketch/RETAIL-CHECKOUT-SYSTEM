import React, { createContext, useState, useEffect } from 'react';

export const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
    const [token, setToken] = useState(localStorage.getItem('token'));
    const [user, setUser] = useState(null);
    const [stores, setStores] = useState([]);
    const [activeStore, setActiveStore] = useState(null);
    const [loading, setLoading] = useState(true);

    const login = (jwtToken, userData, userStores) => {
        localStorage.setItem('token', jwtToken);
        setToken(jwtToken);
        setUser(userData);
        setStores(userStores);
        
        if (userStores && userStores.length > 0) {
            const defaultStore = userStores[0].id;
            setActiveStore(defaultStore);
            localStorage.setItem('activeStore', defaultStore);
        }
    };

    const logout = () => {
        localStorage.removeItem('token');
        localStorage.removeItem('activeStore');
        setToken(null);
        setUser(null);
        setStores([]);
        setActiveStore(null);
    };

    const changeStore = (storeId) => {
        setActiveStore(storeId);
        localStorage.setItem('activeStore', storeId);
    };

    const fetchMe = async (currentToken) => {
        if (!currentToken) {
            setLoading(false);
            return;
        }

        try {
            const savedStore = localStorage.getItem('activeStore');
            const headers = { 'Authorization': `Bearer ${currentToken}` };
            if (savedStore) {
                headers['X-Store-ID'] = savedStore;
            }

            const res = await fetch('http://localhost:5000/api/auth/me', { headers });
            const data = await res.json();
            
            if (data.success) {
                setUser(data.user);
                setStores(data.stores);
                if (data.active_store) {
                    setActiveStore(data.active_store);
                    localStorage.setItem('activeStore', data.active_store);
                } else if (data.stores && data.stores.length > 0) {
                    setActiveStore(data.stores[0].id);
                    localStorage.setItem('activeStore', data.stores[0].id);
                }
            } else {
                // Token rejected by server - clear it
                logout();
            }
        } catch (error) {
            console.error('Failed to restore session:', error);
            // Network error: keep token so user stays logged in
        } finally {
            setLoading(false);
        }
    };

    // Only run on MOUNT to restore an existing saved session from localStorage.
    // login() sets all state directly from the /login response, so no re-fetch needed.
    useEffect(() => {
        const savedToken = localStorage.getItem('token');
        fetchMe(savedToken);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const getAuthHeaders = () => {
        const headers = {};
        if (token) headers['Authorization'] = `Bearer ${token}`;
        if (activeStore) headers['X-Store-ID'] = activeStore.toString();
        return headers;
    };

    return (
        <AuthContext.Provider value={{
            token,
            user,
            stores,
            activeStore,
            loading,
            login,
            logout,
            changeStore,
            getAuthHeaders
        }}>
            {children}
        </AuthContext.Provider>
    );
};
