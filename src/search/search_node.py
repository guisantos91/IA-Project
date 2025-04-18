'''
 # @ Authors: 
 #  - Pedro Pinto (pmap@ua.pt)
 #  - Joao Pinto (jpapinto@ua.pt)
 #  - Guilherme Santos (gui.santos91@ua.pt)
 # @ Create Time: 2024-10-13
 '''

class SearchNode:
    def __init__(self, state, parent, cost=0, heuristic=0, action=None): 
        self.state = state
        self.parent = parent
        self.depth = parent.depth + 1 if parent != None else 0
        self.cost = cost
        self.heuristic = heuristic
        self.action = action

    def __str__(self):
        return "no(" + str(self.state) + "," + str(self.parent) + ")"
    def __repr__(self):
        return str(self)
    def __hash__(self):
        return hash(str(self.state))
    # def __lt__(self, other):
    #     ## A* search
    #     # return (self.cost + self.heuristic) < (other.cost + other.heuristic)
    #     ## Greedy search
    #     return self.heuristic < other.heuristic
    
    def in_parent(self, newstate):
        
        if self.parent is None:
            return False
        
        if all(b in self.parent.state["body"] for b in newstate["body"]) and self.parent.state["traverse"] == newstate["traverse"]:
            return True
        
        # if newstate["body"][0] in self.parent.state["body"] and self.parent.state["traverse"] == newstate["traverse"]:
        #     return True
        
        return self.parent.in_parent(newstate)

    
