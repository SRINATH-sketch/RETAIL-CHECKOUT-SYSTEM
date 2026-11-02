import {useState} from 'react';
import './Chatbot.css';

function Chatbot() {
  const[open,setOpen]=useState(false);
  const[message,setMessage]=useState("");
  const[messages,setMessages]=useState([]);

  const sendMessage=async () => {
      console.log(message);
      setMessages((prev) => [...prev,message]);
      setMessage("");

      const response = await fetch("http://127.0.0.1:5000/api/chat", {
      method: "POST",
      headers:{
        "Content-Type":"application/json",
      },
      body:JSON.stringify({
        message:message
      })
    });
    const data = await response.json();
    console.log(data);
    setMessages((prev) => [...prev, data.response]);
    };

  return (
    <div>
      <button className="chat-button" onClick={() => setOpen(!open)}>💬</button>
      {open && (
      <div className="chat-window">

        <div className="chat-header">
          <h3>AI Assistance</h3>
          <button className="close-button" onClick={() => setOpen(false)}>X</button>
        </div>

        <div className="chat-body">
          <p>Bot: Hello! How can I help you?</p> 
          {messages.map((msg,index) => (
              <p key={index}>YOU: {msg}</p>
          ))}
        </div>

        <div className="chat-input">
          <input type="text" placeholder="Type a message..."
          value={message}
          onChange={(e) => setMessage(e.target.value)}/>
          <button onClick={sendMessage}>➤</button>
        </div>

      </div>
      )}
    </div>
  );
}

export default Chatbot;