import numpy as np
import json
from functions import Prometheufunctions 
from tensorflow.keras.models import Sequential # type: ignore
from tensorflow.keras.layers import Dense  #type: ignore
from tensorflow.keras.optimizers import Adam # type: ignore
from tensorflow.keras.losses import MeanSquaredError  # type: ignore
from tensorflow.keras.losses import Huber  # type: ignore
from collections import deque
import os
import tensorflow as tf
import time
losses = []
rewards = []

class DQNAgent:
    def __init__(self, state_size):
        self.state_size = state_size
        self.memory = deque(maxlen=2000)
        self.gamma = 0.9
        self.epsilon = 1.0
        self.epsilon_min = 0.01
        self.epsilon_decay = 0.995
        self.action = [-2, -1, 0, 1, 2]
        self.model = self._build_model()
        self.target_model = self._build_model() 
        self.update_target_model()  

    def _build_model(self):
        #print(f'At build model State size: {self.state_size}')
        model = Sequential()
        model.add(Dense(16, input_dim=self.state_size, activation='relu'))
        model.add(Dense(32, activation='relu'))
        model.add(Dense(16, activation='relu'))
        model.add(Dense(len(self.action), activation='linear'))
        model.compile(optimizer=Adam(learning_rate=0.001), loss=Huber())
        return model

    def update_target_model(self):
        
        self.target_model.set_weights(self.model.get_weights())

    def remember(self, state, action, reward, next_state):
        self.memory.append((state, action, reward, next_state))

    def act(self, state):
        if np.random.rand() <= self.epsilon:
            return np.random.choice(self.action,p=[0.15,0.25,0.3,0.20,0.1])
        state = np.array([state])  # Add batch dimension
        q_values = self.model.predict(state, verbose=1)
        return self.action[np.argmax(q_values[0])]

    def reward(self, data):
        RTT = int(round(float(data.getRTT())))
        return data.fetchState()[0] + (1 / (1 + RTT / 250) if RTT < 250 else -2)

    def replay(self, batch_size):
        minibatch = np.random.choice(len(self.memory), batch_size, replace=False)
        
        for i in minibatch:
            state = np.array([self.memory[i][0]])
            action = self.memory[i][1]
            reward = self.memory[i][2]
            next_state = np.array([self.memory[i][3]])

            # Predict Q-values for next state using the target network
            q_values_next = self.target_model.predict(next_state, verbose=1)
            target_q = reward + self.gamma * np.amax(q_values_next[0])

            # Update Q-value for the selected action
            q_values = self.model.predict(state, verbose=1)
            q_values[0][action] = target_q

            # Train the model
            history = self.model.fit(state, q_values, epochs=10)
            loss = history.history['loss'][0]
            losses.append(loss)
            rewards.append(reward)

        # Log metrics
        print(f"Average Loss: {np.mean(losses)}, Recent Reward: {reward}")

        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay


def Post(agent,state,step_count):
    action = agent.act(state)
    target_pods = max(1, min(Prometheufunctions().fetchState()[2] + action, 10))

    print(f'Step of Randomnes {step_count}')
    file = '/tmp/shared_file.json'

    # Write scaling action
    with open(file, 'w') as file:
        json.dump({'action': int(target_pods)}, file)

    # Wait for Kubernetes to reach the target
    start_time = time.time()
    #keda might have a bug. When reaching max Replicas e.g. 10 and trying to scale down to 9, it fails
    #to perform the operation. In the other hand all the other scaling actions work properly
    
    while Prometheufunctions().fetchState()[2] != target_pods:
        elapsed_time = time.time() - start_time  # Calculate the elapsed time
        if elapsed_time > 60:
            print("Timeout exceeded while waiting for pods to scale.")
            return False
            #print("Timeout waiting for pods to scale.")
        
        time.sleep(5)
    return action

def main():
    data = Prometheufunctions()
    state = data.fetchState()
    state_size = 3
    agent = DQNAgent(state_size)

    batch_size = 64
    replay_frequency = 64
    target_update_frequency = 50
    step_count = 0


    while 1:
        step_count += 1
        
        # Perform the action
        action = False
        while not action:
            action = Post(agent, state, step_count)
        time.sleep(180)
        next_state = data.fetchState()
        reward = agent.reward(data)

        # Remember the experience
        agent.remember(state, int(action), reward, next_state)
        state = next_state
        
        # Train the agent (experience replay) 
        if len(agent.memory) > batch_size and step_count % replay_frequency == 0:
            print("To do training")
            agent.replay(batch_size)

        # Update the target network every 100 steps
        if step_count % target_update_frequency == 0:
            
            print("Updating Values of Target!")
            agent.update_target_model()
            

if __name__ == '__main__':
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
    tf.get_logger().setLevel('ERROR')
    main()