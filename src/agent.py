'''
 # @ Authors: 
 #  - Pedro Pinto (pmap@ua.pt)
 #  - Joao Pinto (jpapinto@ua.pt)
 #  - Guilherme Santos (gui.santos91@ua.pt)
 # @ Create Time: 2024-10-13
 '''
import asyncio
import getpass
import os
import websockets
import json
import logging
import random
import heapq
from datetime import datetime, timedelta

## Search
from src.search.search_problem import SearchProblem
from src.search.search_tree import SearchTree
from src.snake_game import SnakeGame

## Mapping & Exploration
from src.matrix_operations import MatrixOperations
from src.mapping import Mapping

## Utils
from src.utils.logger import Logger
from src.utils.exceptions import TimeLimitExceeded
from consts import Tiles

DIRECTION_TO_KEY = {
    "NORTH": "w",
    "WEST": "a",
    "SOUTH": "s",
    "EAST": "d"
}

wslogger = logging.getLogger("websockets")
wslogger.setLevel(logging.INFO)



class Agent:
    """Autonomous AI client."""
    
    def __init__(self, server_address, agent_name):
        
        ## Utils
        self.logger = Logger(f"[{agent_name}]", f"logs/{agent_name}.log")
        self.server_address = server_address
        self.agent_name = agent_name
        self.websocket = None
        
        ## Defined by the start of the game
        self.mapping = None 
        self.fps = None
        self.timeout = None
        self.domain = None
        
        ## Action controller
        self.actions_plan = []
        self.action = None
        self.current_goal = None
        self.perfect_effects = False
        
    
    # ----- Main Loop -----
    
    async def run(self):
        """Start the execution of the agent"""
        await self.connect()
        await self.play()
    
    async def connect(self):
        """Connect to the server via websocket"""
        self.websocket = await websockets.connect(f"ws://{self.server_address}/player")
        await self.websocket.send(json.dumps({"cmd": "join", "name": self.agent_name}))

        self.logger.info(f"Connected to server {self.server_address}")
        self.logger.debug(f"Waiting for game information")
        
        map_info = json.loads(await self.websocket.recv())
        self.mapping = Mapping(matrix=map_info["map"])
        
        self.fps = map_info["fps"]
        self.timeout = map_info["timeout"]
        
        self.domain = SnakeGame(
            width=self.mapping.width, 
            height=self.mapping.height, 
            internal_walls=self.mapping.walls
        )
        
    async def play(self):
        """Main loop of the agent, where the game is played"""
        while True:
            try:
                state = json.loads(await self.websocket.recv())

                if not state.get("body"):
                    self.logger.warning("Game Over!")
                    break
                
                self.logger.debug(f"Received state. Step: [{state["step"]}]")
                
                ## --- Main Logic ---
                self.observe(state)
                self.think(time_limit=self.ts + timedelta(seconds=1/(self.fps+1)))
                await self.act()
                ## ------------------
                
                self.logger.debug(f"Time elapsed: {(datetime.now() - self.ts).total_seconds()}")
                                 
            except websockets.exceptions.ConnectionClosedOK:
                self.logger.warning("Server has cleanly disconnected us")                  
    
    # ------ Observe ------
    
    def observe(self, state):
        self.ts = datetime.fromisoformat(state["ts"])
        self.perfect_effects = self.domain.is_perfect_effects(state)
        
        ## Update the mapping
        self.mapping.update(state)
    
    # ------- Act --------

    async def act(self):
        """Send the action to the server"""
        self.logger.debug(f"Action: [{self.action}] in [{self.domain.actions(self.mapping.state)}]")
        
        if self._action_not_possible():
            # Big problem, because the agent is trying to do something that is not possible
            # Can happen if the sync between the agent and the server is not perfect
            # TODO: handle this situation
            self.logger.critical(f"\33[31mAction not possible! [{self.action}]\33[0m")
            self.action = self._get_fast_action(warning=True)
        
        await self.websocket.send(json.dumps({"cmd": "key", "key": DIRECTION_TO_KEY[self.action]})) # mapping to the server key
        
    def _action_not_possible(self):
        return self.action not in self.domain.actions(self.mapping.state)
    
    # ------ Think -------
    
    def think(self, time_limit):
        ## Follow the action plain (nothing new observed)
        if len(self.actions_plan) != 0 and self.mapping.nothing_new_observed(self.perfect_effects):
            self.action = self.actions_plan.pop()
            return
        
        ## Find a new goal
        self.current_goal = self._find_goal()
        self.logger.info(f"New goal {self.current_goal}")
        
        ## Create search structures
        self.problem = SearchProblem(self.domain, initial=self.mapping.state, goal=self.current_goal["position"])
        self.tree = SearchTree(self.problem, 'A*')
        
        ## Search for the solution
        try: 
            solution = self.tree.search(time_limit=time_limit)
        except TimeLimitExceeded as e:
            self.logger.warning(e.args[0])
            self.solution = self._get_fast_action(warning=True)
            return
        
        ## No solution found
        if not solution:
            self.logger.warning("No solution found!")
            self.solution = self._get_fast_action(warning=True)
            return
        
        ## Save the solution as a plan of actions
        self.actions_plan = self.tree.inverse_plan
        self.action = self.actions_plan.pop()
        
        self.logger.debug(f"Actions plan founded! avg_branching: {self.tree.avg_branching}")

    def _find_goal(self):
        """Find a new goal based on mapping and state"""
        new_goal = {}
        
        if self.mapping.observed(Tiles.FOOD):
            new_goal["strategy"] = "food"
            new_goal["position"] = self.mapping.closest_object(Tiles.FOOD)
            
        elif self.mapping.observed(Tiles.SUPER) and not self.perfect_effects:
            new_goal["strategy"] = "super"
            new_goal["position"] = self.mapping.closest_object(Tiles.SUPER)
            
        else:
            new_goal["strategy"] = "exploration"
            new_goal["position"] = self.mapping.next_exploration()
            # Avoid self-searching
            if new_goal["position"] == self.mapping.state["body"][0]:
                new_goal["position"] = self.mapping.next_exploration()
        
        return new_goal

    def _get_fast_action(self, warning=True):
        """Non blocking fast action"""
        # TODO: make an heuristic to choose the best action (non-blocking)
        if warning:
            print("\33[31mFast action!\33[0m")

        # return random.choice(self.domain.actions(self.mapping.state))

        ## A* heuristic
        head = self.mapping.state["body"][0]
        goal = self.current_goal["position"]
        dx = abs(head[0] - goal[0])
        dy = abs(head[1] - goal[1])
        if dx > dy:
            action = "WEST" if head[0] > goal[0] else "EAST"
        else:
            action = "NORTH" if head[1] > goal[1] else "SOUTH"
        
        ## Check if the action is possible
        if action in self.domain.actions(self.mapping.state):
            return action
        else:
            
            if self.domain.actions(self.mapping.state):
                return random.choice(self.domain.actions(self.mapping.state))
            else:
                self.logger.warning(f"Fast action not possible [{action}]")
                return random.choice(["NORTH", "WEST", "SOUTH", "EAST"])
                
