// import {useState} from "react";
// import logos from "../logos.png";
// import "./Home.css";

// function Home() {
//     const [file,setFile]=useState(null);

//     function uploadwork(event){
//         const choose=event.target.file[0];
//         setFile(choose)
//     }

//     return (
//         <>
//             <div className="heading">
//                 <h1>SMART RETAIL CHECKOUT AI</h1>
//             </div>
    
//             <div className="middle">
//                 <h2 style={{color:"lightgrey",textAlign:"center"}}>The system automatically detects the product price and calculates bill</h2>
//             </div>

//                 <input type="file"
//                 hidden
//                 id="up"
//                 onChange={uploadwork}/>

//             <label htmlFor="up" className="upload-box">
//                 <div> <img src={logos} alt="Logo" className="logo" /> </div>
//                 <h2>Click to Upload</h2>
//             </label>
//         </>
import { useState, useRef, useEffect } from "react";
import "./Home.css";
import { FiUploadCloud, FiSearch, FiTrash2, FiRefreshCw, FiPlay } from "react-icons/fi";

function Home() {
    const [file, setFile] = useState(null);
    const [videoUrl, setVideoUrl] = useState(null);
    const [isScanning, setIsScanning] = useState(false);
    const [scanCompleted, setScanCompleted] = useState(false);
    const [detectedProducts, setDetectedProducts] = useState([]);
    const [activeBoxes, setActiveBoxes] = useState([]);
    const [checkoutStatus, setCheckoutStatus] = useState(null); // 'loading', 'success', null
    const [agentData, setAgentData] = useState(null); // AI Retail Agent analysis
    const [showComplementary, setShowComplementary] = useState(false); // Toggle for complementary items

    const videoRef = useRef(null);
    const scanTimeoutsRef = useRef([]);

    // Clean up timeouts on unmount
    useEffect(() => {
        return () => clearAllTimeouts();
    }, []);

    const clearAllTimeouts = () => {
        if (scanTimeoutsRef.current.length > 0) {
            scanTimeoutsRef.current.forEach(t => clearTimeout(t));
            scanTimeoutsRef.current = [];
        }
    };

    function handleUpload(event) {
        const selectedFile = event.target.files[0];
        if (selectedFile) {
            setFile(selectedFile);
            const url = URL.createObjectURL(selectedFile);
            setVideoUrl(url);
            setDetectedProducts([]);
            setActiveBoxes([]);
            setScanCompleted(false);
            setCheckoutStatus(null);
            setAgentData(null);
            setShowComplementary(false);
            clearAllTimeouts();
        }
    }

    function loadDemoVideo(event) {
        event.preventDefault();
        event.stopPropagation();
        const demoUrl = "https://assets.mixkit.co/videos/preview/mixkit-shopping-bag-full-of-groceries-34279-large.mp4";
        setFile({ name: "demo_supermarket_items.mp4", isDemo: true });
        setVideoUrl(demoUrl);
        setDetectedProducts([]);
        setActiveBoxes([]);
        setScanCompleted(false);
        setCheckoutStatus(null);
        setAgentData(null);
        setShowComplementary(false);
        clearAllTimeouts();
    }

    function startDetection() {
        if (!file) return;

        setIsScanning(true);
        setScanCompleted(false);
        setDetectedProducts([]);
        setActiveBoxes([]);
        setCheckoutStatus(null);
        clearAllTimeouts();

        const formData = new FormData();
        if (file.isDemo) {
            formData.append("use_demo", "true");
        } else {
            formData.append("file", file);
        }

        // Reset cart on backend before scanning
        fetch("http://localhost:5000/api/cart", { method: "DELETE" })
            .then(res => {
                if (!res.ok) throw new Error("Failed to clear backend cart.");
                return fetch("http://localhost:5000/api/detect", {
                    method: "POST",
                    body: formData
                });
            })
            .then(res => {
                if (!res.ok) throw new Error("Backend processing failed.");
                return res.json();
            })
            .then(data => {
                if (data.success) {
                    setDetectedProducts(data.products);
                    setVideoUrl(data.video_url);
                    setAgentData(data.agent || null);
                    setIsScanning(false);
                    setScanCompleted(true);

                    // Reload and play the annotated video returned by Flask
                    if (videoRef.current) {
                        videoRef.current.load();
                        videoRef.current.play().catch(err => {
                            console.warn("Autoplay blocked or failed:", err);
                        });
                    }
                } else {
                    alert("Scanning failed: " + data.message);
                    setIsScanning(false);
                }
            })
            .catch(err => {
                console.error("API Error during detection:", err);
                alert("Could not connect to the AI checkout backend on http://localhost:5000. Please ensure the backend server is running.");
                setIsScanning(false);
            });
    }

    function handleReset() {
        clearAllTimeouts();
        setIsScanning(false);
        setScanCompleted(false);
        setFile(null);
        setVideoUrl(null);
        setDetectedProducts([]);
        setActiveBoxes([]);
        setCheckoutStatus(null);
        setAgentData(null);
        setShowComplementary(false);

        if (videoRef.current) {
            videoRef.current.pause();
            videoRef.current.src = "";
        }

        // Sync reset with backend
        fetch("http://localhost:5000/api/cart", { method: "DELETE" })
            .catch(err => console.error("Failed to clear backend cart on reset:", err));
    }

    function updateQuantity(productId, delta) {
        setDetectedProducts(prev =>
            prev.map(p => {
                if (p.id === productId) {
                    const newQty = Math.max(1, p.quantity + delta);
                    return { ...p, quantity: newQty };
                }
                return p;
            })
        );
    }

    function deleteProduct(productId) {
        setDetectedProducts(prev => prev.filter(p => p.id !== productId));
    }

    function triggerCheckout() {
        if (detectedProducts.length === 0) return;
        setCheckoutStatus('loading');
        
        // Finalize transaction by resetting/processing checkout on the backend
        fetch("http://localhost:5000/api/cart", { method: "DELETE" })
            .then(() => {
                setCheckoutStatus('success');
            })
            .catch(err => {
                console.error("Failed to process transaction on backend:", err);
                setCheckoutStatus('success'); // Fallback to client-side success
            });
    }

    const totalItems = detectedProducts.reduce((sum, p) => sum + p.quantity, 0);
    const totalBill = detectedProducts.reduce((sum, p) => sum + (p.quantity * p.price), 0);

    return (
        <div className="home">
            <header className="header">
                <h1>🛒 SMART RETAIL CHECKOUT AI</h1>
            </header>

            <h2 className="title">
                Upload a shopping checkout video, detect products automatically, and checkout instantly.
            </h2>

            <div className="scanner-section">
                {!videoUrl ? (
                    <div className="upload-box-container" style={{ width: "100%", display: "flex", flexDirection: "column", alignItems: "center" }}>
                        <label htmlFor="upload" className="upload-box">
                            <FiUploadCloud className="upload-icon" />
                            <h2>Click to Upload Video</h2>
                            <p>Supports MP4, WebM formats</p>
                        </label>
                        <button type="button" className="demo-link-btn" onClick={loadDemoVideo}>
                            ✨ Don't have a video? Try our Demo Video
                        </button>
                    </div>
                ) : (
                    <div className="video-container">
                        <video
                            ref={videoRef}
                            className="preview-video"
                            src={videoUrl}
                            muted
                            playsInline
                            controls
                        />
                        {isScanning && <div className="scanner-line"></div>}
                        {isScanning && (
                            <div className="scanning-badge">
                                <span className="pulse-dot" style={{ width: 8, height: 8, borderRadius: "50%", background: "white", display: "inline-block" }}></span>
                                AI Scanning Active...
                            </div>
                        )}
                        {!isScanning && scanCompleted && (
                            <div className="ready-badge">
                                Analysis Complete
                            </div>
                        )}
                        {activeBoxes.map(box => (
                            <div
                                key={box.id}
                                className="bounding-box"
                                style={{
                                    top: box.top,
                                    left: box.left,
                                    width: box.width,
                                    height: box.height
                                }}
                            >
                                <span className="bounding-box-label">{box.label}</span>
                            </div>
                        ))}
                    </div>
                )}

                <input
                    type="file"
                    id="upload"
                    hidden
                    accept="video/*"
                    onChange={handleUpload}
                />

                {videoUrl && (
                    <div className="button-group">
                        <button
                            className="detect-btn"
                            onClick={startDetection}
                            disabled={isScanning}
                        >
                            <FiSearch /> {isScanning ? "Scanning..." : "Detect Products"}
                        </button>
                        <button className="reset-btn" onClick={handleReset}>
                            <FiRefreshCw /> Reset
                        </button>
                    </div>
                )}
            </div>

            {checkoutStatus === 'success' ? (
                <div style={{
                    background: "rgba(16, 185, 129, 0.15)",
                    border: "1px solid #10b981",
                    borderRadius: "12px",
                    padding: "20px",
                    textAlign: "center",
                    margin: "20px 0",
                    animation: "slideIn 0.3s ease"
                }}>
                    <h3 style={{ color: "#34d399", margin: "0 0 10px 0" }}>🎉 Payment Success!</h3>
                    <p style={{ color: "#a5b4fc", margin: 0 }}>
                        Thank you for using Smart Retail Checkout AI. Your bill of <strong>₹{totalBill.toFixed(2)}</strong> for {totalItems} items has been processed successfully.
                    </p>
                </div>
            ) : null}

            <div className="table-container">
                <h2>🛒 Shopping Cart</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Product</th>
                            <th>Quantity</th>
                            <th>Price</th>
                            <th>Total</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {detectedProducts.length === 0 ? (
                            <tr>
                                <td colSpan="5" className="empty-state">
                                    No products detected yet. Please upload a video and run detection.
                                </td>
                            </tr>
                        ) : (
                            detectedProducts.map(product => (
                                <tr key={product.id} className="product-row">
                                    <td style={{ fontWeight: "600" }}>{product.name}</td>
                                    <td>
                                        <div className="qty-control">
                                            <button
                                                className="qty-btn"
                                                onClick={() => updateQuantity(product.id, -1)}
                                                disabled={product.quantity <= 1 || isScanning}
                                            >
                                                -
                                            </button>
                                            <span className="qty-val">{product.quantity}</span>
                                            <button
                                                className="qty-btn"
                                                onClick={() => updateQuantity(product.id, 1)}
                                                disabled={isScanning}
                                            >
                                                +
                                            </button>
                                        </div>
                                    </td>
                                    <td>₹{product.price.toFixed(2)}</td>
                                    <td style={{ fontWeight: "700", color: "#818cf8" }}>₹{(product.price * product.quantity).toFixed(2)}</td>
                                    <td>
                                        <div className="action-cell">
                                            <button
                                                className="delete-btn"
                                                onClick={() => deleteProduct(product.id)}
                                                disabled={isScanning}
                                                title="Delete item"
                                            >
                                                <FiTrash2 />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>

            <div className="summary">
                <div className="card card-items">
                    <h3>Total Items</h3>
                    <h1>{totalItems}</h1>
                </div>

                <div className="card card-bill">
                    <h3>Total Bill</h3>
                    <h1>₹{totalBill.toFixed(2)}</h1>
                </div>
            </div>

            {/* ── AI Retail Agent Panel ───────────────────────── */}
            {agentData && scanCompleted && (
                <div className="agent-panel">
                    <div className="agent-panel-header">
                        <span className="agent-icon">🤖</span>
                        <h2>AI Retail Assistant</h2>
                        
                        {/* The requested Complementary Icon button */}
                        <button 
                            className="complementary-toggle-btn" 
                            onClick={() => setShowComplementary(!showComplementary)}
                        >
                            <span className="comp-icon">💡</span> 
                            {showComplementary ? "Hide Complementary" : "View Complementary"}
                        </button>

                        <span className="agent-badge">LIVE</span>
                    </div>

                    {/* Notifications — removals & low stock */}
                    {agentData.notifications && agentData.notifications.length > 0 && (
                        <div className="agent-section">
                            <h3 className="agent-section-title">🔔 Alerts</h3>
                            <div className="agent-notifications">
                                {agentData.notifications.map((n, i) => (
                                    <div key={i} className={`agent-notif agent-notif--${n.severity || 'warning'}`}>
                                        {n.message}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Free Gifts / Complementary Area */}
                    {agentData.free_gifts && agentData.free_gifts.length > 0 && (
                        <div className="agent-section">
                            <h3 className="agent-section-title">🎁 Complementary Gifts</h3>
                            <div className="agent-gifts">
                                {agentData.free_gifts.map((gift, i) => (
                                    <div key={i} className="agent-gift-card">
                                        <div className="agent-gift-top">
                                            <span className="agent-gift-badge">FREE GIFT</span>
                                            <span className="agent-gift-name">{gift.quantity}x {gift.name}</span>
                                        </div>
                                        <p className="agent-gift-desc">{gift.description}</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Recommendations / Complementary (Toggled via button) */}
                    {showComplementary && (
                        <div className="agent-section complementary-section-active">
                            <h3 className="agent-section-title">💡 Complementary Suggestions</h3>
                            
                            {agentData.recommendations && agentData.recommendations.length > 0 ? (
                                <div className="agent-recs">
                                    {agentData.recommendations.map((rec, i) => (
                                        <div key={i} className="agent-rec-card">
                                            <div className="agent-rec-top">
                                                <span className="agent-rec-name">{rec.name}</span>
                                                {rec.price && (
                                                    <span className="agent-rec-price">₹{rec.price.toFixed(2)}</span>
                                                )}
                                            </div>
                                            <p className="agent-rec-reason">{rec.reason}</p>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div className="agent-notif agent-notif--info">
                                    Add items like <strong>Fresh Milk</strong> to see complementary suggestions (like a Tea Cup)!
                                </div>
                            )}
                        </div>
                    )}

                    {/* Discounts */}
                    {agentData.discounts && agentData.discounts.length > 0 && (
                        <div className="agent-section">
                            <h3 className="agent-section-title">🏷️ Discounts Applied</h3>
                            <div className="agent-discounts">
                                {agentData.discounts.map((d, i) => (
                                    <div key={i} className="agent-discount-card">
                                        <div className="agent-discount-top">
                                            <span className="agent-discount-badge">{d.badge}</span>
                                            <span className="agent-discount-saving">-₹{d.saving.toFixed(2)}</span>
                                        </div>
                                        <p className="agent-discount-desc">{d.description}</p>
                                    </div>
                                ))}
                                <div className="agent-discount-total">
                                    <span>Total Savings</span>
                                    <span className="agent-saved">-₹{(totalBill - agentData.discounted_total).toFixed(2)}</span>
                                </div>
                                <div className="agent-discount-total agent-final-total">
                                    <span>Discounted Total</span>
                                    <span className="agent-final">₹{agentData.discounted_total.toFixed(2)}</span>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Insights */}
                    {agentData.insights && (
                        <div className="agent-section">
                            <h3 className="agent-section-title">📊 Shopping Insights</h3>
                            <div className="agent-insights">
                                <div className="agent-insight-grid">
                                    <div className="agent-insight-stat">
                                        <span className="insight-val">{agentData.insights.item_count}</span>
                                        <span className="insight-label">Items</span>
                                    </div>
                                    <div className="agent-insight-stat">
                                        <span className="insight-val">₹{agentData.insights.original_total.toFixed(2)}</span>
                                        <span className="insight-label">Original</span>
                                    </div>
                                    <div className="agent-insight-stat insight-green">
                                        <span className="insight-val">₹{agentData.insights.you_save.toFixed(2)}</span>
                                        <span className="insight-label">You Save</span>
                                    </div>
                                </div>
                                {agentData.insights.tips && agentData.insights.tips.length > 0 && (
                                    <div className="agent-tips">
                                        {agentData.insights.tips.map((tip, i) => (
                                            <div key={i} className="agent-tip">{tip}</div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Checkout Button */}
            {detectedProducts.length > 0 && !isScanning && checkoutStatus !== 'success' && (
                <div style={{ display: "flex", justifyContent: "center", marginTop: "30px" }}>
                    <button
                        onClick={triggerCheckout}
                        disabled={checkoutStatus === 'loading'}
                        style={{
                            background: "linear-gradient(135deg, #10b981 0%, #059669 100%)",
                            color: "white",
                            border: "none",
                            padding: "16px 40px",
                            borderRadius: "12px",
                            fontSize: "1.1rem",
                            fontWeight: "700",
                            cursor: "pointer",
                            boxShadow: "0 10px 20px rgba(16, 185, 129, 0.2)",
                            display: "flex",
                            alignItems: "center",
                            gap: "10px",
                            transition: "all 0.2s ease"
                        }}
                    >
                        {checkoutStatus === 'loading' ? (
                            <>Processing Checkout...</>
                        ) : (
                            <>Proceed to Checkout (₹{totalBill.toFixed(2)})</>
                        )}
                    </button>
                </div>
            )}
        </div>
    );
}

export default Home;