  # Vision Service

  by [2060.io](https://2060.io) — Capture and verify human biometrics with a simple API for biometric verification flows.

  ---

  ![Basic deployment](./docs/diagrams/basic-deployment.png)

  ---

  ## About 2060.io

  2060.io builds open-source tools for creating rich, decentralized, chat-powered services.
  We enable next-generation authentication, messaging, and Verifiable Credentials workflows—combining text, images, video, voice, and biometric authentication, all underpinned by privacy, interoperability, and the power of self-sovereign identity.

  ---

  ## Project Overview

  Vision is a toolkit for biometric verification, orchestrated through Vision Service, which offers an API for handling flows. It uses video calls handled by a WebRTC server to capture live streams and determines liveness, comparing them to reference images through a Face Matcher service. Implementors control user enrollment and video call initiation.

  ---

  ## Deployment Diagram

  Vision Service integrates seamlessly into a system managed by a Controller to handle verification flows. The Controller supplies the resources to gather subject data necessary for verification, as illustrated below:

  ![Basic deployment](./docs/diagrams/basic-deployment.png)

  The Vision Service uses a Mediasoup client to join WebRTC video calls, ensuring a secure connection for liveness testing. See [WebRTC Server](https://github.com/2060-io/webrtc-server).

  ---

  ## Who Is This For?

  - Developers needing to integrate biometric verification into their systems with a customizable API.
  - Those requiring secure, real-time identity verification over video.
  - Teams seeking biometric verification tools compatible with decentralized systems and Verifiable Credentials.

  ---

  ## API

  The Vision Service API allows you to initiate and manage verification flows. 
  Results are asynchronously posted to the callbacks you implement.

  ### Join Call (/join-call)

  Initiate a biometric verification flow with this endpoint:

  ```json
  POST /join-call
  Content-Type: application/json

  {
    "ws_url": "wss://your-webrtc-server:443/?roomId=xxx&peerId=xxx",
    "datastore_base_url": "https://your-datastore-url",
    "callback_base_url": "https://your-callback-url",
    "token": "{UUID}",
    "lang": "en"
  }
  ```
  - `ws_url`: WebSocket URL for joining the video call.
  - `callback_base_url`: Base URL for callbacks from Vision Service.
  - `datastore_base_url`: (Optional) Base URL for retrieving reference images.
  - `token`: Unique identifier for your flow to be used in callbacks.
  - `lang`: Supported languages, currently 'es' and 'en'.

  ### Callbacks

  Implement the following endpoints to handle vision service callbacks:

  #### Reference Image List (GET)

  Get reference images related to a flow:

  - **Endpoint:** `[callbackBaseUrl]/list/:token`
  - **Response:** JSON array of data URLs or regular URLs for images.

  #### Success (PUT)

  Triggered upon successful verification:

  - **Endpoint:** `[callbackBaseUrl]/success/:token`

  #### Failure (PUT)

  Triggered upon verification failure:

  - **Endpoint:** `[callbackBaseUrl]/failure/:token`

  ---

  ## How to Run Locally

  ### Option 1: Traditional Installation

  1. **Clone the repository:**

  ```bash
  git clone ...
  cd vision-service
  ```

  2. **Create a Python environment (recommended):**

  ```bash
  python -m venv myenv
  source myenv/bin/activate # For Linux/macOS
  .\myenv\Scripts\activate # For Windows
  ```

  3. **Install dependencies:**

  ```bash
  pip install -r requirements.txt
  ```

  4. **Set up environment:**

  Create an `.env` file with configuration variables.

  5. **Start Application:**

  ```bash
  python main.py
  ```

  ### Option 2: Docker Installation

  1. **Build Docker image:**

  ```bash
  docker build -t vision-service .
  ```

  2. **Run Docker container:**

  ```bash
  docker run -d --network host vision-service
  ```

  *Note: Use host networking for WebRTC compatibility.*

  ---

  ## Testing

  To test the service, ensure external components are running, or use demo deployments.

  ### Test Controller Setup

  Use the demo controller in the `test` directory:

  1. Place a reference image in `test/assets`, e.g., `1234.jpg`.
  2. Run the demo controller:

  ```bash
  PUBLIC_BASE_URL=http://my-ip:5001 python callbacks.py
  ```

  ### Create Room and Live Stream

  Connect through [WebRTC WebClient](https://webrtc-webclient.dev.2060.io) and obtain the Invitation Link.

  ### Run Vision Service

  Follow local or Docker setup instructions, specifying `VISION_MATCHER_BASE_URL`. Use http://vision-matcher.demos.dev.2060.io or run locally with Docker:

  ```bash
  docker run -p 5123:5123 io2060/vision-matcher:latest
  ```

  ### Start Verification Flow

  Make a POST request to Vision Service:

  ```bash
  curl -X POST http://localhost:5000/join-call \
      -H "Content-Type: application/json" \
      -d '{"ws_url":"wss://[WEBRTC_SERVER_HOST]:443/?roomId=[ROOM_ID]&peerId=192324","callback_base_url":"[PUBLIC_BASE_URL]","token":"[REFERENCE_IMAGE_FILENAME]","lang":"en"}'
  ```

  - Replace placeholders with your values from the steps above.

  ---

  ## Features

  - Real-time, video-based biometric verification.
  - API-first approach with flexible deployment options.
  - Integration-ready with support for custom flows.

  ---

  ## Security and Privacy

  - Local processing ensures privacy.
  - Open-source for community audit and enhancement.
  - WebRTC connectivity for secure liveness testing.

  ---

  ## Contributing and Support

  Pull requests, issue reporting, and further integrations are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for contributing guidelines.

  - [GitHub Issues](https://github.com/2060-io/vision-service/issues)
  - Learn more: [https://2060.io](https://2060.io)

  ---

  ## License

  This project is licensed under the [GNU Affero General Public License](LICENSE).