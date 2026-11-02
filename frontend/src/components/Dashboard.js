import React, { useContext, useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { AuthContext } from '../context/AuthContext';
import {
    FiShoppingCart, FiLogOut, FiGrid, FiBox, FiActivity,
    FiTrendingUp, FiAlertTriangle, FiDollarSign, FiSearch,
    FiEye, FiX, FiCheckCircle, FiPlusCircle, FiUsers,
    FiTrash2, FiRefreshCw, FiZap, FiPlus
} from 'react-icons/fi';
import {
    ResponsiveContainer, AreaChart, Area, BarChart, Bar,
    XAxis, YAxis, Tooltip, CartesianGrid, Legend, Cell
} from 'recharts';
import './Dashboard.css';

const CHART_COLORS = ['#818cf8', '#34d399', '#fbbf24', '#f87171', '#38bdf8', '#a78bfa', '#f472b6', '#4ade80'];

const Dashboard = () => {
    const { user, stores, activeStore, changeStore, logout, getAuthHeaders } = useContext(AuthContext);
    const navigate = useNavigate();

    // Redirect non-admin users to checkout scanner
    useEffect(() => {
        if (user && user.role !== 'admin') {
            navigate('/checkout');
        }
    }, [user, navigate]);

    // Filters
    const [selectedStore, setSelectedStore] = useState(activeStore ? activeStore.toString() : 'all');
    const [dateRange, setDateRange] = useState('7d');

    // Analytics Data State
    const [overview, setOverview] = useState({
        total_revenue: 0,
        total_transactions: 0,
        total_items_sold: 0,
        average_order_value: 0,
        active_customers: 0,
        low_stock_count: 0
    });
    const [salesTrends, setSalesTrends] = useState([]);
    const [hourlyTrends, setHourlyTrends] = useState([]);
    const [topProducts, setTopProducts] = useState([]);
    const [lowStockItems, setLowStockItems] = useState([]);
    const [transactions, setTransactions] = useState([]);
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedTransaction, setSelectedTransaction] = useState(null);
    const [restockingId, setRestockingId] = useState(null);

    // Interactive Modals and Actions
    const [showResetModal, setShowResetModal] = useState(false);
    const [showQuickPurchaseModal, setShowQuickPurchaseModal] = useState(false);
    const [isResetting, setIsResetting] = useState(false);
    const [isSeeding, setIsSeeding] = useState(false);
    const [isQuickPurchasing, setIsQuickPurchasing] = useState(false);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [toast, setToast] = useState(null);
    const [highlightedTxId, setHighlightedTxId] = useState(null);

    const prevTxCountRef = useRef(null);
    const toastTimeoutRef = useRef(null);

    const showToastNotification = useCallback((message, type = 'info') => {
        if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
        setToast({ message, type });
        toastTimeoutRef.current = setTimeout(() => {
            setToast(null);
        }, 4000);
    }, []);

    // Sync selectedStore when activeStore changes
    useEffect(() => {
        if (activeStore && selectedStore !== 'all' && selectedStore !== activeStore.toString()) {
            setSelectedStore(activeStore.toString());
        }
    }, [activeStore, selectedStore]);

    const fetchAnalytics = useCallback((isSilent = false) => {
        if (!isSilent) setIsRefreshing(true);
        const headers = getAuthHeaders();
        const storeParam = selectedStore === 'all' ? 'all' : selectedStore;

        const pOverview = fetch(`http://localhost:5000/api/analytics/overview?store_id=${storeParam}&date_range=${dateRange}`, { headers })
            .then(r => r.json()).catch(() => null);
        const pTrends = fetch(`http://localhost:5000/api/analytics/sales-trend?store_id=${storeParam}&date_range=${dateRange}`, { headers })
            .then(r => r.json()).catch(() => null);
        const pHourly = fetch(`http://localhost:5000/api/analytics/hourly-trend?store_id=${storeParam}&date_range=${dateRange}`, { headers })
            .then(r => r.json()).catch(() => null);
        const pTop = fetch(`http://localhost:5000/api/analytics/top-products?store_id=${storeParam}&date_range=${dateRange}&limit=8`, { headers })
            .then(r => r.json()).catch(() => null);
        const pLow = fetch(`http://localhost:5000/api/analytics/low-stock?store_id=${storeParam}&threshold=20`, { headers })
            .then(r => r.json()).catch(() => null);
        const pTx = fetch(`http://localhost:5000/api/analytics/transactions?store_id=${storeParam}&date_range=${dateRange}`, { headers })
            .then(r => r.json()).catch(() => null);

        Promise.all([pOverview, pTrends, pHourly, pTop, pLow, pTx])
            .then(([resOverview, resTrends, resHourly, resTop, resLow, resTx]) => {
                if (resOverview?.success) setOverview(resOverview.overview);
                if (resTrends?.success) setSalesTrends(resTrends.trends || []);
                if (resHourly?.success) setHourlyTrends(resHourly.trends || []);
                if (resTop?.success) setTopProducts(resTop.top_products || []);
                if (resLow?.success) setLowStockItems(resLow.low_stock || []);
                
                if (resTx?.success) {
                    const newTxList = resTx.transactions || [];
                    // Detect if a new customer purchase was added while viewing the dashboard
                    if (prevTxCountRef.current !== null && newTxList.length > prevTxCountRef.current) {
                        const latest = newTxList[0];
                        if (latest) {
                            setHighlightedTxId(latest.id);
                            showToastNotification(`🎉 New customer purchase detected! ₹${Number(latest.amount).toFixed(2)} added to dashboard.`, 'success');
                            setTimeout(() => setHighlightedTxId(null), 5000);
                        }
                    }
                    prevTxCountRef.current = newTxList.length;
                    setTransactions(newTxList);
                }
            })
            .finally(() => {
                if (!isSilent) setIsRefreshing(false);
            });
    }, [selectedStore, dateRange, getAuthHeaders, showToastNotification]);

    // Initial load and periodic polling (every 4 seconds) to detect customer purchases in real-time
    useEffect(() => {
        fetchAnalytics();

        const interval = setInterval(() => {
            fetchAnalytics(true);
        }, 4000);

        const handleVisibilityChange = () => {
            if (!document.hidden) {
                fetchAnalytics(true);
            }
        };
        document.addEventListener('visibilitychange', handleVisibilityChange);

        return () => {
            clearInterval(interval);
            document.removeEventListener('visibilitychange', handleVisibilityChange);
            if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
        };
    }, [fetchAnalytics]);

    const handleStoreChange = (e) => {
        const val = e.target.value;
        setSelectedStore(val);
        if (val !== 'all') {
            changeStore(parseInt(val));
        }
    };

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    // Reset All: Sets all values on the dashboard to zero
    const handleResetAll = () => {
        setIsResetting(true);
        const storeParam = selectedStore === 'all' ? 'all' : selectedStore;
        fetch('http://localhost:5000/api/analytics/reset', {
            method: 'POST',
            headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({ store_id: storeParam })
        })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    setOverview({
                        total_revenue: 0,
                        total_transactions: 0,
                        total_items_sold: 0,
                        average_order_value: 0,
                        active_customers: 0,
                        low_stock_count: 0
                    });
                    setSalesTrends([]);
                    setHourlyTrends([]);
                    setTopProducts([]);
                    setLowStockItems([]);
                    setTransactions([]);
                    prevTxCountRef.current = 0;
                    setShowResetModal(false);
                    showToastNotification('🧹 All values on the dashboard have been reset to zero.', 'info');
                    fetchAnalytics(true);
                } else {
                    alert('Reset failed: ' + data.message);
                }
            })
            .catch(err => console.error('Reset error:', err))
            .finally(() => setIsResetting(false));
    };

    // Load Demo Data: Populates realistic demo amounts, sales trends, items, and transactions
    const handleLoadDemoData = () => {
        setIsSeeding(true);
        const storeParam = selectedStore === 'all' ? (activeStore || 1) : selectedStore;
        fetch('http://localhost:5000/api/analytics/seed-demo', {
            method: 'POST',
            headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({ store_id: storeParam })
        })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    showToastNotification(`✨ Demo amount (₹${Number(data.total_revenue || 0).toFixed(2)}) and 25 sales orders loaded successfully!`, 'success');
                    fetchAnalytics(false);
                } else {
                    alert('Failed to load demo data: ' + data.message);
                }
            })
            .catch(err => console.error('Seed demo error:', err))
            .finally(() => setIsSeeding(false));
    };

    // Quick Simulated Customer Purchase
    const handleQuickPurchase = (preset) => {
        setIsQuickPurchasing(true);
        const storeParam = selectedStore === 'all' ? (activeStore || 1) : parseInt(selectedStore);
        fetch('http://localhost:5000/api/analytics/quick-purchase', {
            method: 'POST',
            headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({
                store_id: storeParam,
                customer_name: preset.customer,
                customer_email: preset.email,
                payment_method: preset.payment,
                items: preset.items
            })
        })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    setShowQuickPurchaseModal(false);
                    showToastNotification(`🛍️ Customer purchase of ₹${Number(data.total_amount).toFixed(2)} recorded and added to dashboard!`, 'success');
                    if (data.transaction_id) {
                        setHighlightedTxId(data.transaction_id);
                        setTimeout(() => setHighlightedTxId(null), 5000);
                    }
                    fetchAnalytics(true);
                } else {
                    alert('Purchase failed: ' + data.message);
                }
            })
            .catch(err => console.error('Quick purchase error:', err))
            .finally(() => setIsQuickPurchasing(false));
    };

    const handleRestock = (productId, amount = 50) => {
        setRestockingId(productId);
        fetch('http://localhost:5000/api/analytics/restock', {
            method: 'POST',
            headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({
                store_id: selectedStore === 'all' ? (activeStore || 1) : parseInt(selectedStore),
                product_id: productId,
                quantity: amount
            })
        })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    fetchAnalytics(true);
                    showToastNotification(`📦 Restocked ${amount} units of ${productId}`, 'success');
                } else {
                    alert('Failed to restock product: ' + data.message);
                }
            })
            .catch(err => console.error('Restock error:', err))
            .finally(() => setRestockingId(null));
    };

    const openTransactionDetail = (txId) => {
        fetch(`http://localhost:5000/api/analytics/transactions/${txId}`, { headers: getAuthHeaders() })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    setSelectedTransaction(data.transaction);
                }
            })
            .catch(err => console.error('Failed to load transaction details:', err));
    };

    const filteredTransactions = transactions.filter(t => {
        if (!searchQuery) return true;
        const q = searchQuery.toLowerCase();
        return (
            t.id.toString().includes(q) ||
            (t.customer_name && t.customer_name.toLowerCase().includes(q)) ||
            (t.customer_email && t.customer_email.toLowerCase().includes(q)) ||
            (t.store_name && t.store_name.toLowerCase().includes(q))
        );
    });

    const isDashboardZero = overview.total_transactions === 0 && overview.total_revenue === 0;

    return (
        <div className="dashboard-root">
            {/* Toast Notification Banner */}
            {toast && (
                <div className={`dash-toast ${toast.type}`}>
                    <span>{toast.message}</span>
                    <button className="dash-toast-close" onClick={() => setToast(null)} title="Dismiss">
                        <FiX />
                    </button>
                </div>
            )}

            {/* Top Header Navbar */}
            <nav className="dash-navbar">
                <div className="dash-brand">
                    <div className="dash-brand-logo">🛒</div>
                    <div>
                        <span className="dash-brand-name">SmartRetail AI</span>
                        <span className="dash-brand-tag">Owner Analytics Hub</span>
                    </div>
                </div>

                <div className="dash-nav-center">
                    {/* Store Selector */}
                    <div className="dash-filter-pill">
                        <FiGrid className="dash-icon" />
                        <select value={selectedStore} onChange={handleStoreChange} className="dash-select">
                            <option value="all">🌐 All Accessible Stores</option>
                            {stores.map(s => (
                                <option key={s.id} value={s.id.toString()}>
                                    🏬 {s.name}
                                </option>
                            ))}
                        </select>
                    </div>

                    {/* Date Range Selector */}
                    <div className="dash-date-pills">
                        {[
                            { key: 'today', label: 'Today' },
                            { key: '7d', label: 'Last 7 Days' },
                            { key: '30d', label: 'Last 30 Days' },
                            { key: 'all', label: 'All Time' }
                        ].map(d => (
                            <button
                                key={d.key}
                                className={`dash-date-btn ${dateRange === d.key ? 'active' : ''}`}
                                onClick={() => setDateRange(d.key)}
                            >
                                {d.label}
                            </button>
                        ))}
                    </div>
                </div>

                <div className="dash-nav-right">
                    <button className="dash-scan-cta" onClick={() => navigate('/checkout')}>
                        <FiActivity />
                        <span>AI Checkout</span>
                    </button>
                    <div className="dash-user-chip">
                        <div className="dash-avatar">
                            {user?.full_name ? user.full_name[0].toUpperCase() : 'A'}
                        </div>
                        <div className="dash-user-info">
                            <span className="dash-username">{user?.full_name || 'Admin'}</span>
                            <span className="dash-user-role">Owner Dashboard</span>
                        </div>
                    </div>
                    <button className="dash-logout-btn" onClick={handleLogout} title="Logout">
                        <FiLogOut />
                    </button>
                </div>
            </nav>

            {/* Main Content Area */}
            <main className="dash-main">
                {/* Dashboard Action Bar */}
                <div className="dash-action-bar">
                    <div className="dash-action-left">
                        <div className="dash-live-status">
                            <span className="dash-pulse-dot"></span>
                            <span>POS Live Feed: Auto-Syncing</span>
                        </div>
                    </div>
                    <div className="dash-action-right">
                        <button
                            className="dash-btn-action demo"
                            onClick={handleLoadDemoData}
                            disabled={isSeeding}
                            title="Generate realistic demo amounts and orders"
                        >
                            <FiZap />
                            <span>{isSeeding ? "Loading Demo..." : "Load Demo Data"}</span>
                        </button>

                        <button
                            className="dash-btn-action simulate"
                            onClick={() => setShowQuickPurchaseModal(true)}
                            title="Simulate a customer purchase to see live addition"
                        >
                            <FiPlus />
                            <span>Simulate Purchase</span>
                        </button>

                        <button
                            className="dash-btn-action refresh"
                            onClick={() => fetchAnalytics(false)}
                            disabled={isRefreshing}
                            title="Refresh data"
                        >
                            <FiRefreshCw className={isRefreshing ? "spin-icon" : ""} />
                            <span>{isRefreshing ? "Syncing..." : "Refresh"}</span>
                        </button>

                        <button
                            className="dash-btn-action reset"
                            onClick={() => setShowResetModal(true)}
                            title="Reset all values on the dashboard to zero"
                        >
                            <FiTrash2 />
                            <span>Reset All</span>
                        </button>
                    </div>
                </div>

                {/* Zero State Guidance Banner */}
                {isDashboardZero && (
                    <div className="dash-zero-banner">
                        <div className="dash-zero-info">
                            <span className="dash-zero-icon">0️⃣</span>
                            <div>
                                <h3>All Dashboard Values Are Currently Reset to Zero</h3>
                                <p>
                                    Ready for live shopping! When a customer purchases, values automatically add and display in real-time.
                                    You can test with <strong>Simulate Purchase</strong>, checkout via <strong>AI Checkout</strong>, or load demo numbers with <strong>Load Demo Data</strong>.
                                </p>
                            </div>
                        </div>
                        <div className="dash-zero-actions">
                            <button className="dash-zero-btn-demo" onClick={handleLoadDemoData} disabled={isSeeding}>
                                <FiZap /> Load Demo Data
                            </button>
                            <button className="dash-zero-btn-sim" onClick={() => setShowQuickPurchaseModal(true)}>
                                <FiPlus /> Simulate Customer Purchase
                            </button>
                            <button className="dash-zero-btn-scan" onClick={() => navigate('/checkout')}>
                                <FiActivity /> Open AI Checkout Scanner
                            </button>
                        </div>
                    </div>
                )}

                {/* Executive KPI Cards */}
                <div className="dash-kpi-grid">
                    <div className="dash-kpi-card purple">
                        <div className="dash-kpi-top">
                            <div className="dash-kpi-icon purple"><FiDollarSign /></div>
                            <span className="dash-kpi-badge positive"><FiTrendingUp /> Live</span>
                        </div>
                        <div className="dash-kpi-val">₹{overview.total_revenue.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
                        <div className="dash-kpi-label">Total Sales Revenue</div>
                    </div>

                    <div className="dash-kpi-card green">
                        <div className="dash-kpi-top">
                            <div className="dash-kpi-icon green"><FiShoppingCart /></div>
                            <span className="dash-kpi-badge neutral">Completed</span>
                        </div>
                        <div className="dash-kpi-val">{overview.total_transactions}</div>
                        <div className="dash-kpi-label">Total Transactions</div>
                    </div>

                    <div className="dash-kpi-card blue">
                        <div className="dash-kpi-top">
                            <div className="dash-kpi-icon blue"><FiBox /></div>
                            <span className="dash-kpi-badge neutral">Units</span>
                        </div>
                        <div className="dash-kpi-val">{overview.total_items_sold}</div>
                        <div className="dash-kpi-label">Total Items Sold</div>
                    </div>

                    <div className="dash-kpi-card yellow">
                        <div className="dash-kpi-top">
                            <div className="dash-kpi-icon yellow"><FiTrendingUp /></div>
                            <span className="dash-kpi-badge neutral">Average</span>
                        </div>
                        <div className="dash-kpi-val">₹{overview.average_order_value.toFixed(2)}</div>
                        <div className="dash-kpi-label">Avg. Order Value (AOV)</div>
                    </div>

                    <div className="dash-kpi-card amber">
                        <div className="dash-kpi-top">
                            <div className="dash-kpi-icon amber"><FiAlertTriangle /></div>
                            {overview.low_stock_count > 0 && (
                                <span className="dash-kpi-badge warning">{overview.low_stock_count} Alert</span>
                            )}
                        </div>
                        <div className="dash-kpi-val">{overview.low_stock_count}</div>
                        <div className="dash-kpi-label">Low Stock Warnings (&lt;20)</div>
                    </div>

                    <div className="dash-kpi-card cyan">
                        <div className="dash-kpi-top">
                            <div className="dash-kpi-icon cyan"><FiUsers /></div>
                            <span className="dash-kpi-badge neutral">Active</span>
                        </div>
                        <div className="dash-kpi-val">{overview.active_customers}</div>
                        <div className="dash-kpi-label">Active Customers</div>
                    </div>
                </div>

                {/* Charts Grid */}
                <div className="dash-charts-grid">
                    {/* Revenue Trend Area Chart */}
                    <div className="dash-chart-card full-width">
                        <div className="dash-chart-header">
                            <div>
                                <h2>📈 Sales Revenue &amp; Order Volume Trend</h2>
                                <p>Track total earnings and daily transaction frequency</p>
                            </div>
                            <span className="dash-pill-tag">Timeline Analytics</span>
                        </div>
                        <div className="dash-chart-body">
                            {salesTrends.length > 0 ? (
                                <ResponsiveContainer width="100%" height={280}>
                                    <AreaChart data={salesTrends} margin={{ top: 10, right: 30, left: 10, bottom: 0 }}>
                                        <defs>
                                            <linearGradient id="colorRevenue" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="5%" stopColor="#818cf8" stopOpacity={0.4} />
                                                <stop offset="95%" stopColor="#818cf8" stopOpacity={0.0} />
                                            </linearGradient>
                                            <linearGradient id="colorTx" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="5%" stopColor="#34d399" stopOpacity={0.4} />
                                                <stop offset="95%" stopColor="#34d399" stopOpacity={0.0} />
                                            </linearGradient>
                                        </defs>
                                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                                        <XAxis dataKey="date" stroke="#94a3b8" />
                                        <YAxis yAxisId="left" stroke="#818cf8" tickFormatter={(v) => `₹${v}`} />
                                        <YAxis yAxisId="right" orientation="right" stroke="#34d399" />
                                        <Tooltip
                                            contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#f8fafc' }}
                                            formatter={(val, name) => [name === 'Revenue (₹)' ? `₹${Number(val).toFixed(2)}` : val, name]}
                                        />
                                        <Legend wrapperStyle={{ paddingTop: '10px' }} />
                                        <Area yAxisId="left" type="monotone" dataKey="revenue" name="Revenue (₹)" stroke="#818cf8" strokeWidth={3} fillOpacity={1} fill="url(#colorRevenue)" />
                                        <Area yAxisId="right" type="monotone" dataKey="transactions" name="Transactions Count" stroke="#34d399" strokeWidth={2} fillOpacity={1} fill="url(#colorTx)" />
                                    </AreaChart>
                                </ResponsiveContainer>
                            ) : (
                                <div className="dash-empty-chart">
                                    <p>Values currently reset to zero. Make a customer purchase or click "Load Demo Data" to plot sales trends.</p>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Top Products Bar Chart */}
                    <div className="dash-chart-card">
                        <div className="dash-chart-header">
                            <div>
                                <h2>🏆 Top Selling Products</h2>
                                <p>Best performing inventory by units sold</p>
                            </div>
                        </div>
                        <div className="dash-chart-body">
                            {topProducts.length > 0 ? (
                                <ResponsiveContainer width="100%" height={260}>
                                    <BarChart data={topProducts} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                                        <XAxis dataKey="product_name" stroke="#94a3b8" interval={0} angle={-25} textAnchor="end" height={50} />
                                        <YAxis stroke="#94a3b8" />
                                        <Tooltip
                                            contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#f8fafc' }}
                                            formatter={(val, name) => [val, name === 'units_sold' ? 'Units Sold' : name]}
                                        />
                                        <Bar dataKey="units_sold" name="Units Sold" radius={[6, 6, 0, 0]}>
                                            {topProducts.map((entry, index) => (
                                                <Cell key={`cell-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                                            ))}
                                        </Bar>
                                    </BarChart>
                                </ResponsiveContainer>
                            ) : (
                                <div className="dash-empty-chart">
                                    <p>No products sold yet. Products will appear as customers purchase.</p>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Peak Hours Bar Chart */}
                    <div className="dash-chart-card">
                        <div className="dash-chart-header">
                            <div>
                                <h2>⏰ Peak Shopping Hours</h2>
                                <p>Distribution of orders throughout the day</p>
                            </div>
                        </div>
                        <div className="dash-chart-body">
                            {hourlyTrends.length > 0 ? (
                                <ResponsiveContainer width="100%" height={260}>
                                    <BarChart data={hourlyTrends} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                                        <XAxis dataKey="hour" stroke="#94a3b8" />
                                        <YAxis stroke="#94a3b8" />
                                        <Tooltip
                                            contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#f8fafc' }}
                                            formatter={(val, name) => [name === 'revenue' ? `₹${Number(val).toFixed(2)}` : val, name === 'revenue' ? 'Sales Revenue' : 'Orders']}
                                        />
                                        <Bar dataKey="revenue" name="Sales Revenue (₹)" fill="#38bdf8" radius={[4, 4, 0, 0]} />
                                    </BarChart>
                                </ResponsiveContainer>
                            ) : (
                                <div className="dash-empty-chart">
                                    <p>No peak shopping data recorded for this period.</p>
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* Low Stock Warning & Restock Section */}
                <div className="dash-section-container">
                    <div className="dash-section-title-wrap">
                        <div>
                            <h2>⚠️ Low Stock Inventory Warnings</h2>
                            <p>Products requiring immediate inventory replenishment (&lt; 20 units)</p>
                        </div>
                        <span className="dash-count-badge amber">{lowStockItems.length} Products Low</span>
                    </div>

                    {lowStockItems.length === 0 ? (
                        <div className="dash-all-good-box">
                            <FiCheckCircle className="dash-good-icon" />
                            <span>Stock health is excellent! All products are adequately supplied.</span>
                        </div>
                    ) : (
                        <div className="dash-low-stock-grid">
                            {lowStockItems.map((item, idx) => (
                                <div key={idx} className="dash-low-stock-card">
                                    <div className="dash-stock-top">
                                        <span className="dash-stock-name">{item.product_name}</span>
                                        <span className={`dash-stock-count ${item.stock <= 5 ? 'critical' : 'warning'}`}>
                                            {item.stock} in stock
                                        </span>
                                    </div>
                                    <div className="dash-stock-progress-bar">
                                        <div
                                            className={`dash-stock-progress-fill ${item.stock <= 5 ? 'critical' : 'warning'}`}
                                            style={{ width: `${Math.min(100, (item.stock / 20) * 100)}%` }}
                                        ></div>
                                    </div>
                                    <div className="dash-stock-meta">
                                        <span>Unit Price: ₹{Number(item.price).toFixed(2)}</span>
                                        <span>Store: {item.store_name}</span>
                                    </div>
                                    <div className="dash-restock-actions">
                                        <button
                                            className="dash-restock-btn"
                                            disabled={restockingId === item.product_id}
                                            onClick={() => handleRestock(item.product_id, 50)}
                                        >
                                            <FiPlusCircle /> {restockingId === item.product_id ? 'Restocking...' : '+50 Units'}
                                        </button>
                                        <button
                                            className="dash-restock-btn secondary"
                                            disabled={restockingId === item.product_id}
                                            onClick={() => handleRestock(item.product_id, 100)}
                                        >
                                            +100
                                        </button>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* Transaction & Customer Purchase History Table */}
                <div className="dash-section-container">
                    <div className="dash-table-header-wrap">
                        <div>
                            <h2>📜 Transaction &amp; Customer History</h2>
                            <p>Real-time log of processed sales, invoices, and customer receipts</p>
                        </div>
                        <div className="dash-search-box">
                            <FiSearch className="dash-search-icon" />
                            <input
                                type="text"
                                placeholder="Search by customer name, email, TX ID..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                className="dash-search-input"
                            />
                            {searchQuery && (
                                <button className="dash-search-clear" onClick={() => setSearchQuery('')}>
                                    <FiX />
                                </button>
                            )}
                        </div>
                    </div>

                    <div className="dash-table-wrap">
                        <table className="dash-table">
                            <thead>
                                <tr>
                                    <th>TX ID</th>
                                    <th>Date &amp; Time</th>
                                    <th>Store</th>
                                    <th>Customer</th>
                                    <th>Payment Method</th>
                                    <th>Items</th>
                                    <th>Total Amount</th>
                                    <th>Status</th>
                                    <th>Action</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filteredTransactions.length === 0 ? (
                                    <tr>
                                        <td colSpan="9" className="dash-empty-td">
                                            {isDashboardZero ? (
                                                <div style={{ padding: '24px', textAlign: 'center' }}>
                                                    <span style={{ fontSize: '1.5rem', display: 'block', marginBottom: '8px' }}>🛒</span>
                                                    <strong>Dashboard values are reset to zero.</strong>
                                                    <p style={{ color: '#94a3b8', margin: '6px 0 0' }}>
                                                        When a customer purchases, their invoice will immediately display here.
                                                    </p>
                                                </div>
                                            ) : (
                                                "No transactions match your search filter."
                                            )}
                                        </td>
                                    </tr>
                                ) : (
                                    filteredTransactions.map(t => (
                                        <tr key={t.id} className={t.id === highlightedTxId ? 'highlight-row' : ''}>
                                            <td className="dash-tx-id">#{t.id}</td>
                                            <td className="dash-tx-date">{new Date(t.created_at).toLocaleString()}</td>
                                            <td>{t.store_name}</td>
                                            <td>
                                                <div className="dash-tx-cust-name">{t.customer_name}</div>
                                                <small className="dash-tx-cust-email">{t.customer_email}</small>
                                            </td>
                                            <td>
                                                <span className="dash-payment-pill">{t.payment_method || 'Card'}</span>
                                            </td>
                                            <td>{t.total_units || t.item_types_count || 1} units</td>
                                            <td className="dash-tx-amount">₹{Number(t.amount).toFixed(2)}</td>
                                            <td>
                                                <span className="dash-status-badge completed">
                                                    <FiCheckCircle /> Completed
                                                </span>
                                            </td>
                                            <td>
                                                <button
                                                    className="dash-view-btn"
                                                    onClick={() => openTransactionDetail(t.id)}
                                                >
                                                    <FiEye /> View Receipt
                                                </button>
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            </main>

            {/* Reset All Confirmation Modal */}
            {showResetModal && (
                <div className="dash-modal-overlay" onClick={() => setShowResetModal(false)}>
                    <div className="dash-modal-content reset-confirm-modal" onClick={e => e.stopPropagation()}>
                        <div className="dash-modal-header danger">
                            <div>
                                <h3>⚠️ Reset All Dashboard Values to Zero</h3>
                                <p>Confirm clearing all sales metrics, transactions, and revenue data</p>
                            </div>
                            <button className="dash-modal-close" onClick={() => setShowResetModal(false)}>
                                <FiX />
                            </button>
                        </div>
                        <div className="dash-modal-body">
                            <p style={{ color: '#e2e8f0', fontSize: '1rem', lineHeight: '1.6', marginBottom: '14px' }}>
                                Are you sure you want to <strong>reset all values on the dashboard to zero</strong>?
                            </p>
                            <ul className="dash-reset-list">
                                <li>Total Sales Revenue will be set to <strong>₹0.00</strong></li>
                                <li>Total Transactions will be set to <strong>0</strong></li>
                                <li>Total Items Sold will be set to <strong>0</strong></li>
                                <li>Average Order Value will be set to <strong>₹0.00</strong></li>
                                <li>Active Customers count will be set to <strong>0</strong></li>
                                <li>Sales Trends, Peak Hours &amp; Top Products charts will be cleared</li>
                                <li>All transaction receipts and sales records will be cleared</li>
                            </ul>
                            <p style={{ color: '#a5b4fc', fontSize: '0.88rem', marginTop: '16px', background: 'rgba(99, 102, 241, 0.1)', padding: '10px 14px', borderRadius: '8px', border: '1px solid rgba(99, 102, 241, 0.2)' }}>
                                💡 Tip: You can restore realistic numbers anytime using the <strong>"Load Demo Data"</strong> button, or test new checkouts using <strong>"Simulate Purchase"</strong>.
                            </p>
                        </div>
                        <div className="dash-modal-footer">
                            <button className="dash-btn-secondary" onClick={() => setShowResetModal(false)} disabled={isResetting}>
                                Cancel
                            </button>
                            <button className="dash-btn-danger" onClick={handleResetAll} disabled={isResetting}>
                                <FiTrash2 /> {isResetting ? "Resetting..." : "Yes, Reset All to Zero"}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Quick Simulated Customer Purchase Modal */}
            {showQuickPurchaseModal && (
                <div className="dash-modal-overlay" onClick={() => setShowQuickPurchaseModal(false)}>
                    <div className="dash-modal-content quick-buy-modal" onClick={e => e.stopPropagation()}>
                        <div className="dash-modal-header">
                            <div>
                                <h3>🛍️ Simulate Customer Purchase</h3>
                                <p>Test real-time addition to dashboard revenue and transaction metrics</p>
                            </div>
                            <button className="dash-modal-close" onClick={() => setShowQuickPurchaseModal(false)}>
                                <FiX />
                            </button>
                        </div>
                        <div className="dash-modal-body">
                            <p style={{ color: '#94a3b8', fontSize: '0.92rem', marginBottom: '16px' }}>
                                Choose a sample customer basket to complete a checkout. The transaction amount will immediately add and display on your dashboard!
                            </p>
                            <div className="dash-presets-grid">
                                {[
                                    {
                                        title: 'Breakfast Essentials',
                                        customer: 'Rahul Sharma',
                                        email: 'rahul.sharma@gmail.com',
                                        payment: 'UPI',
                                        total: 170.00,
                                        itemsText: '2x Fresh Milk (₹100) + 1x Whole Wheat Bread (₹70)',
                                        items: [
                                            { product_id: 'milk', name: 'Fresh Milk', quantity: 2, price: 50.00 },
                                            { product_id: 'bread', name: 'Whole Wheat Bread', quantity: 1, price: 70.00 }
                                        ]
                                    },
                                    {
                                        title: 'Evening Tea & Biscuits',
                                        customer: 'Priya Patel',
                                        email: 'priya.p@outlook.com',
                                        payment: 'Card',
                                        total: 155.00,
                                        itemsText: '1x Masala Tea (₹35) + 2x Tea Cup (₹60) + 2x Cream Biscuits (₹60)',
                                        items: [
                                            { product_id: 'tea', name: 'Masala Tea Packet', quantity: 1, price: 35.00 },
                                            { product_id: 'cup', name: 'Tea Cup', quantity: 2, price: 30.00 },
                                            { product_id: 'biscuits', name: 'Cream Biscuits', quantity: 2, price: 30.00 }
                                        ]
                                    },
                                    {
                                        title: 'Organic Fruits Pack',
                                        customer: 'Amit Verma',
                                        email: 'amit.verma@gmail.com',
                                        payment: 'UPI',
                                        total: 240.00,
                                        itemsText: '2x Organic Bananas (₹120) + 3x Red Apple (₹120)',
                                        items: [
                                            { product_id: 'banana', name: 'Organic Bananas', quantity: 2, price: 60.00 },
                                            { product_id: 'apple', name: 'Red Apple', quantity: 3, price: 40.00 }
                                        ]
                                    },
                                    {
                                        title: 'Natural Honey & Yogurt',
                                        customer: 'Sneha Reddy',
                                        email: 'sneha.reddy@yahoo.com',
                                        payment: 'Cash',
                                        total: 210.00,
                                        itemsText: '1x Natural Honey (₹120) + 2x Fresh Yogurt (₹90)',
                                        items: [
                                            { product_id: 'honey', name: 'Natural Honey', quantity: 1, price: 120.00 },
                                            { product_id: 'yogurt', name: 'Fresh Yogurt', quantity: 2, price: 45.00 }
                                        ]
                                    }
                                ].map((preset, idx) => (
                                    <div key={idx} className="dash-preset-card">
                                        <div className="dash-preset-header">
                                            <div>
                                                <h4 className="dash-preset-title">{preset.title}</h4>
                                                <small className="dash-preset-customer">Customer: {preset.customer} ({preset.payment})</small>
                                            </div>
                                            <span className="dash-preset-price">₹{preset.total.toFixed(2)}</span>
                                        </div>
                                        <p className="dash-preset-items">{preset.itemsText}</p>
                                        <button
                                            className="dash-preset-btn"
                                            disabled={isQuickPurchasing}
                                            onClick={() => handleQuickPurchase(preset)}
                                        >
                                            <FiShoppingCart /> {isQuickPurchasing ? 'Processing...' : `Purchase (₹${preset.total.toFixed(2)})`}
                                        </button>
                                    </div>
                                ))}
                            </div>
                        </div>
                        <div className="dash-modal-footer">
                            <button className="dash-btn-secondary" onClick={() => setShowQuickPurchaseModal(false)}>
                                Cancel
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Transaction Receipt Details Modal */}
            {selectedTransaction && (
                <div className="dash-modal-overlay" onClick={() => setSelectedTransaction(null)}>
                    <div className="dash-modal-content" onClick={(e) => e.stopPropagation()}>
                        <div className="dash-modal-header">
                            <div>
                                <h3>🧾 Receipt &amp; Transaction Details</h3>
                                <p>Transaction #{selectedTransaction.id} — {new Date(selectedTransaction.created_at).toLocaleString()}</p>
                            </div>
                            <button className="dash-modal-close" onClick={() => setSelectedTransaction(null)}>
                                <FiX />
                            </button>
                        </div>

                        <div className="dash-modal-body">
                            <div className="dash-receipt-meta">
                                <div className="dash-meta-item">
                                    <span>Store Name</span>
                                    <strong>{selectedTransaction.store_name}</strong>
                                </div>
                                <div className="dash-meta-item">
                                    <span>Customer</span>
                                    <strong>{selectedTransaction.customer_name}</strong>
                                    <small>{selectedTransaction.customer_email}</small>
                                </div>
                                <div className="dash-meta-item">
                                    <span>Payment Method</span>
                                    <strong>{selectedTransaction.payment_method || 'Card'}</strong>
                                </div>
                                <div className="dash-meta-item">
                                    <span>Status</span>
                                    <span className="dash-status-badge completed">Completed</span>
                                </div>
                            </div>

                            <h4 className="dash-items-heading">Purchased Items Breakdown</h4>
                            <table className="dash-receipt-table">
                                <thead>
                                    <tr>
                                        <th>Product Name</th>
                                        <th>Qty</th>
                                        <th>Unit Price</th>
                                        <th>Subtotal</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {selectedTransaction.items && selectedTransaction.items.length > 0 ? (
                                        selectedTransaction.items.map((item, idx) => (
                                            <tr key={idx}>
                                                <td>{item.product_name}</td>
                                                <td>{item.quantity}</td>
                                                <td>₹{Number(item.unit_price).toFixed(2)}</td>
                                                <td className="dash-item-subtotal">
                                                    ₹{Number(item.subtotal || item.quantity * item.unit_price).toFixed(2)}
                                                </td>
                                            </tr>
                                        ))
                                    ) : (
                                        <tr>
                                            <td colSpan="4">No itemized breakdown recorded for this transaction.</td>
                                        </tr>
                                    )}
                                </tbody>
                                <tfoot>
                                    <tr>
                                        <td colSpan="3" style={{ textAlign: 'right', fontWeight: 'bold' }}>Total Bill Paid:</td>
                                        <td className="dash-receipt-total">
                                            ₹{Number(selectedTransaction.amount).toFixed(2)}
                                        </td>
                                    </tr>
                                </tfoot>
                            </table>
                        </div>

                        <div className="dash-modal-footer">
                            <button className="dash-btn-secondary" onClick={() => setSelectedTransaction(null)}>
                                Close Receipt
                            </button>
                            <button className="dash-btn-primary" onClick={() => window.print()}>
                                🖨️ Print Receipt
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default Dashboard;
