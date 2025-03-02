### Detailed Plan for Avatar App Enhancements

We will break the plan into very specific tasks and follow a step-by-step approach for each goal, ensuring that all aspects (avatar selection, voice sentiment analysis, emotion tracking, etc.) are implemented efficiently.

#### 1. **Simplify User Interaction and Add Male/Female Avatar Option**

**Goal**: Make the app simpler, with an immediate option for users to choose between male and female avatars, and remove unnecessary setup options.

##### Actions:

- **Avatar Selection**:
  - Offer only two avatars (male and female) to the user on the landing page.
  - Remove complex features like choosing avatar IDs, languages, or knowledge IDs. This will make the app easier to use, especially for elderly users.
- **Navigation**:
  - In the `navbar.tsx`, remove external links to SDKs, API Docs, and other pages irrelevant to the user. Only show options for **"Start Conversation"** and **"Logout"** (if a user authentication flow exists).
- **Immediate Avatar Load**:
  - Once an avatar (male or female) is selected, the conversation should begin immediately. The app should directly go to the speaking mode without requiring the user to click "Start" or choose further options.

##### Testing:

- Run the app and verify that only the essential buttons and avatar choices are visible.
- Ensure that when a user selects an avatar, the app immediately moves to conversation mode without requiring extra clicks.

##### **Granular Steps**:

- Update `navbar.tsx` to remove unnecessary links.
- In `InteractiveAvatar.tsx`, create a simple landing page that lets users select between a male or female avatar.
- After selection, the avatar session starts immediately.

---

#### 2. **Integrate Hume API for Emotion Detection**

**Goal**: Measure user emotions through voice sentiment analysis, store the audio and emotion data with timestamps, and display insights in the UI.

##### Actions:

- **API Route Setup**:
  - Create a new API route at `pages/api/audio-analysis.ts` that receives audio data from the front end and sends it to Hume's API for analysis. This route will also return sentiment/emotion information.
- **Sending Audio to Hume**:
  - In `InteractiveAvatar.tsx`, after every user interaction (e.g., after the avatar speaks or after the user speaks), send the audio to the Hume API. This API call will analyze the emotional state of the user.
- **Store Timestamps**:
  - Capture timestamps for each audio segment sent to Hume. Use the JavaScript `Date.now()` function or a similar method to record the exact time the user interacted with the avatar and their emotional state.
- **Display Emotional Insights**:
  - Display the emotional response data (e.g., happiness, sadness, calmness) on the screen in a simple text or chart format (using a library like Chart.js).

##### Research Required:

- **Hume API Limits**:
  - Check how much audio the Hume API can analyze at a time. Typically, APIs have a limit on how many seconds of audio you can send in a single request.
  - Understand the response format of the Hume API so you can parse it and display it correctly.

##### **Granular Steps**:

1. **Set up API Route**:
   - Create a file at `pages/api/audio-analysis.ts` that will:
     1. Receive the audio data from the client.
     2. Forward it to Hume’s API for analysis.
     3. Return the emotion analysis back to the client.
2. **Send Audio Data**:
   - In `InteractiveAvatar.tsx`, after every interaction, collect and send the audio data to this new API route.
3. **Display Emotion Data**:
   - Parse the emotion response and display it in a user-friendly format (e.g., “User is feeling happy” or display it as a chart).

##### Testing:

- Test if the app successfully sends audio to Hume API after each interaction.
- Test if emotion data is returned and displayed correctly.
- Make sure to test with different emotions to validate the accuracy of the results.

---

#### 3. **Store User Data in ChromaDB and SQLite**

**Goal**: Store user interactions, emotions, and therapeutic history using ChromaDB for vector data and SQLite for structured data.

##### Actions:

- **Vector DB (ChromaDB)**:
  - ChromaDB will be used to store conversation embeddings (numerical representations of conversation text). For each interaction (after the conversation ends), convert the text into embeddings using a transformer model (such as OpenAI's `text-embedding-ada`).
  - Store these embeddings in ChromaDB for future retrieval (e.g., for analyzing long-term therapy progress).
  - Create a new API route in `pages/api/store-vectors.ts` to handle this storage process.
- **Structured Data (SQLite)**:
  - SQLite will store the structured data, such as user profiles (name, age, health conditions) and the timestamped emotion data (from the Hume API). This will create a long-term record of each session.
  - Set up SQLite using `better-sqlite3` or another SQLite library for Node.js.
  - Store each user’s session history, including timestamps, emotions, and conversation data.

##### **Granular Steps**:

1. **Set Up ChromaDB**:
   - Set up a ChromaDB instance for vector storage.
   - Create a backend route (`pages/api/store-vectors.ts`) that:
     1. Converts conversation text to embeddings.
     2. Stores these embeddings in ChromaDB.
2. **Set Up SQLite**:
   - Install SQLite and set up a table schema to store user information (name, age, emotional data, session timestamps).
   - Create API routes (e.g., `pages/api/store-session.ts`) to store user session data after every conversation.

##### Testing:

- Verify that conversations are being stored as vectors in ChromaDB.
- Verify that structured data (e.g., user info and session history) is stored correctly in SQLite.
- Test retrieval of data from both databases to ensure consistency.

---

### Summary of Key Changes

1. **Simplify User Interaction**:

   - Remove unnecessary setup steps and external links.
   - Display only two avatars (male and female) for the user to choose from.

2. **Integrate Hume API**:

   - Set up API routes to send audio data to Hume.
   - Display emotion results and track timestamps for each interaction.

3. **Data Storage (ChromaDB and SQLite)**:
   - Store conversation embeddings in ChromaDB and user information/emotion data in SQLite.
   - Build a long-term therapeutic record for each user.

Once this plan is executed step by step, you will have a functional avatar app tailored for elderly adults, with integrated emotion tracking and data storage. Would you like to start with simplifying the user interface first, or move directly into integrating Hume API for sentiment detection?

Iterations-
The updated plan based on your latest feedback and critique from your superior highlights important structural and technical elements required for the development of your interactive avatar platform. Below is a more granular breakdown of the entire system, incorporating web sockets, voice analysis, user background detection, and more. This is intended to serve as a guiding document for development and can be shared with your team or experts for detailed review.

---

### **Detailed Plan for the Interactive Avatar System**

---

#### **1. Core Infrastructure Setup (Phase 1)**

**Objective**: Establish the backend using **FastAPI** and the frontend using **Next.js** to facilitate WebSocket communication for real-time conversation, while keeping the system scalable and responsive.

**Steps**:

- **Backend**:

  - **FastAPI WebSocket Implementation**: Create an endpoint (`/ws/conversation`) to handle real-time bidirectional communication using `fastapi` and `uvicorn`. Ensure the backend can handle concurrent connections with asynchronous processing.
  - **Text Streaming**: The backend should use OpenAI’s GPT API (via a Flask server in Python) to generate real-time responses and send them back to the frontend via WebSockets.
  - **Frontend WebSocket Integration**: Establish persistent WebSocket connections in the Next.js frontend. Use event listeners to detect user inputs and stream responses back from the backend.

- **Testing**: Ensure real-time message exchange works smoothly and scale the system to handle concurrent connections.

---

#### **2. Simplified Avatar Interaction and UI (Phase 2)**

**Objective**: Remove unnecessary features from the avatar selection and streamline interaction for elderly users. Provide a simple choice between male and female avatars and an intuitive chat interface.

**Steps**:

- **Avatar Selection**: On the frontend, prompt the user to choose between a male or female avatar, as a simple two-button UI component.
- **Remove Unnecessary Links**: Strip away links like SDK, API Docs, and Avatars from the navigation bar. Focus solely on avatar interaction and messaging.
- **Conversation Flow**: Auto-initiate conversation after avatar selection, without requiring manual user actions.
- **Frontend**: Modify the current `InteractiveAvatar.tsx` to include only text interaction and remove any unnecessary setup for voice or knowledge IDs.

---

#### **3. User Background Detection (Phase 3)**

**Objective**: Analyze the user's background using OpenAI’s image API and store this data securely.

**Steps**:

- **Image Capture**: When the session begins, capture a photo of the user via the front-end using the HTML5 camera API (with user consent).
- **Backend**: Send the image to OpenAI’s image analysis API and extract key information (e.g., background color, environment).
- **Data Storage**: Store the results of the background analysis in the SQLite database with a timestamp. This data should influence conversation personalization.
- **Frontend Modifications**: Add camera access prompts and logic to handle image capture and transfer to the backend. If the user declines, gracefully handle this by skipping the background analysis step.

---

#### **4. User Authentication and Authorization (Phase 4)**

**Objective**: Implement basic user authentication for both users and admin.

**Steps**:

- **Backend**:

  - **JWT Authentication**: Secure endpoints using JWTs (JSON Web Tokens) in FastAPI for user login, with roles for Users and Admins.
  - **Admin Features**: The admin login will feature options to manage the knowledge base, such as deleting or adding information in ChromaDB.

- **Frontend**:

  - Implement a basic login page for both users and admin. For admin, provide access to a dashboard that manages the knowledge base.
  - Provide a “forgot password” option that triggers an email to the admin for recovery (as per your requirement).

- **Testing**: Ensure only authenticated users and admins can access the respective features.

---

#### **5. Emotion Detection Using Hume AI (Phase 5)**

**Objective**: Measure the user's emotional state during the conversation and display emotional insights in real-time.

**Steps**:

- **Backend**:

  - **Hume API Integration**: Once the user finishes speaking, the audio data is sent to Hume API for emotion detection. Process the Hume AI JSON response and store the emotional analysis alongside user interaction data with timestamps.
  - **WebSocket Updates**: Continuously send emotion data back to the frontend to update the UI with real-time emotional feedback.

- **Frontend**:

  - **Visual Feedback**: Display emotional indicators on the screen (e.g., an emoji or color gradient to reflect mood). Track and show the user’s emotional trajectory over time in a simple chart or text-based UI.

- **Testing**: Test how accurately emotions are detected and ensure that feedback is shown correctly in real-time.

---

#### **6. WebSocket-Based Real-Time Text Interaction (Phase 6)**

**Objective**: Use WebSocket communication to enhance the speed of interactions between the user, OpenAI’s LLM, and HeyGen avatar text animations.

**Steps**:

- **Frontend WebSocket Setup**: Create a persistent WebSocket connection from the Next.js frontend to the FastAPI backend to send user input and receive AI-generated text in real time.
- **Backend**: OpenAI’s GPT model generates responses based on user input, emotion analysis, and context from ChromaDB.
- **Text-To-Speech (HeyGen)**: Use the HeyGen avatar’s text-based speech animations, based on the text streamed from the backend.
- **Socket Disconnect Handling**: Implement socket reconnection logic to handle dropped connections.

---

#### **7. Knowledge Base Management (Admin Feature) (Phase 7)**

**Objective**: Allow admins to update and manage the knowledge base stored in ChromaDB, using metadata for querying and llama-index for chunking new additions.

**Steps**:

- **Admin Dashboard**: Allow the admin to view existing knowledge entries in ChromaDB, delete them based on metadata, or add new documents.
- **Chunking Strategy**: For adding knowledge, implement LlamaIndex to chunk large documents before generating embeddings.
- **Knowledge Embedding**: Use OpenAI embeddings to store vector representations of text chunks in ChromaDB.
- **Testing**: Test CRUD operations on ChromaDB to ensure the knowledge base is updated correctly.

---

#### **8. Data Storage in ChromaDB and SQLite (Phase 8)**

**Objective**: Store user interaction data, including conversation history and emotional state, in both vector (ChromaDB) and structured (SQLite) databases.

**Steps**:

- **ChromaDB**:

  - Convert conversation history into vector embeddings after each session using OpenAI’s embedding models.
  - Store these embeddings in ChromaDB for easy retrieval during future conversations.

- **SQLite**:

  - Store user data (name, age, etc.) and therapeutic information.
  - Log every conversation with timestamps, emotion data, and session metadata.

- **Testing**: Ensure correct data storage in both ChromaDB and SQLite. Verify the retrieval of stored vector embeddings for personalized conversations.

---

#### **9. Deployment on AWS (Phase 9)**

**Objective**: Deploy the entire application stack on AWS for scalability and availability.

**Steps**:

- **Backend**: Use **AWS ECS** (Elastic Container Service) with **Fargate** to deploy containerized FastAPI and Next.js applications.
- **Database Hosting**: Deploy **PostgreSQL** on AWS RDS for session management and user data. Use AWS EC2 for hosting **ChromaDB**.
- **DNS and SSL**: Use **AWS Route 53** for DNS management and **AWS Certificate Manager** for SSL certificates.
- **Load Balancing and Scaling**: Implement load balancing and auto-scaling with **AWS Application Load Balancer** and configure CloudWatch for monitoring and logging.

---

### **Next Steps**

- **Development Kickoff**: Begin with Phase 1 by setting up FastAPI, Next.js, and basic WebSocket communication.
- **Review Points**: After completing each phase, review the progress and resolve any bugs or issues before moving on to the next phase.
- **Testing and Feedback**: Throughout development, test each new feature or change extensively and gather user feedback to improve the interface and functionality.

This approach ensures a step-by-step integration of core features, making it easier to debug and adapt the system as necessary. Let me know if you need further adjustments or if you're ready to proceed with development!
