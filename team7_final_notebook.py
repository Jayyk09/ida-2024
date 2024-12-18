# -*- coding: utf-8 -*-
"""Team7_Final_Notebook.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1to4OKXg0bGWQEPbCsbZJNj5yffK_Ma17

The following code block installs the simpy library, which is needed to simulate the production, and import other libraries that are necessary.
"""

!pip install simpy

import matplotlib.pyplot as plt
import math
import numpy as np
import pandas as pd
import polars as pl
import seaborn as sns
import simpy
from tqdm.auto import tqdm
import random

"""The following code block defines the simualtion model."""

class ProductionSystem:
    def __init__(
        self,
        env,
        handlers,
        stations,
        component_assignments,
        inventory_allocations,
        reorder_points,
        metrics_dict,
        seed=0,
    ):
        self.env = env
        self.handlers = handlers
        self.stations = stations
        self.metrics_dict = metrics_dict
        self.orders_outstanding = {
            'Station 1': False,
            'Station 2': False,
            'Station 3': False,
            'Station 4': False,
            'Station 5': False,
        }
        self.travel_time_distributions = {
            'Station 1': 5 + (2 + 1.5*handlers.capacity)*np.random.lognormal(sigma=0.2),
            'Station 2': 10 + (2 + 1.5*handlers.capacity)*np.random.lognormal(sigma=0.3),
            'Station 3': 12.5 + (2 + 1.5*handlers.capacity)*np.random.lognormal(sigma=0.4),
            'Station 4': 15 + (2 + 1.5*handlers.capacity)*np.random.lognormal(sigma=0.5),
            'Station 5': 20 + (2 + 1.5*handlers.capacity)*np.random.lognormal(sigma=0.5),
        }
        self.component_assignments = component_assignments
        self.inventory_allocations = inventory_allocations
        self.reorder_points = reorder_points
        self.available_inventory = dict(self.inventory_allocations)
        self.inventory_position = dict(self.available_inventory)

        np.random.seed(seed)

    def process_item(self, vehicle, vehicle_data):
        """Simulate an item moving through five stations."""

        for station in self.stations:
            with self.stations[station].request() as request:
                yield request

                assigned_component = self.component_assignments[station]
                component_variant = vehicle_data[assigned_component]

                if self.available_inventory[component_variant] == 0:
                    self.metrics_dict[f'{assigned_component}_repairs'] += 1
                else:
                    self.available_inventory[component_variant] -= 1
                    self.inventory_position[component_variant] -= 1

                yield self.env.timeout(1)

    def inventory_control(self):
        """Periodically check the level of the gas station tank and call the tank
        truck if the level falls below a threshold."""
        for station in self.stations:
            if not self.orders_outstanding[station]:
                assigned_component = self.component_assignments[station]
                orders = {}
                for component_variant in self.reorder_points:
                    if component_variant.startswith(assigned_component):
                        if self.inventory_position[component_variant] <= self.reorder_points[component_variant]:
                            order_size = self.inventory_allocations[component_variant] - self.available_inventory[component_variant]
                            orders[component_variant] = order_size
                if orders:
                    self.orders_outstanding[station] = True
                    with self.handlers.request() as handler_request:
                        yield handler_request
                        orders = {}
                        for component_variant in self.reorder_points:
                            if component_variant.startswith(assigned_component):
                                if self.inventory_position[component_variant] <= self.reorder_points[component_variant]:
                                    order_size = self.inventory_allocations[component_variant] - self.available_inventory[component_variant]
                                    orders[component_variant] = order_size

                        order_time = self.env.now
                        for ordered_component, ordered_amount in orders.items():
                            self.inventory_position[ordered_component] += ordered_amount

                        yield self.env.timeout(self.travel_time_distributions[station])

                        for ordered_component, ordered_amount in orders.items():
                            self.available_inventory[ordered_component] += ordered_amount
                        self.orders_outstanding[station] = False

def generate_arrivals(env, production_system, vehicle_information):
    """Generate arrivals based on given arrival times."""
    for vehicle, vehicle_data in vehicle_information.items():
        arrival_time = vehicle_data['arrival_time']
        yield env.timeout(arrival_time - env.now)

        env.process(production_system.process_item(vehicle, vehicle_data))
        env.process(production_system.inventory_control())

"""The following code block defines a function to run the simulation model."""

def run_simulation(
    production_data,
    component_assignments,
    inventory_allocations,
    reorder_points,
    num_handlers=1,
    day_start=1,
    day_end=90,
    space_available=100,
) -> dict:

    assigned_components_list = sorted(list(component_assignments.values()))
    assert assigned_components_list == ['CA', 'CB', 'CC', 'CD', 'CE'], "You need to assign each component to a single station"

    total_component_allocations = {
        'CA': 0,
        'CB': 0,
        'CC': 0,
        'CD': 0,
        'CE': 0,
    }
    for cvariant, callocation in inventory_allocations.items():
        if cvariant.startswith('CA'):
            total_component_allocations['CA'] += callocation
        if cvariant.startswith('CB'):
            total_component_allocations['CB'] += callocation
        if cvariant.startswith('CC'):
            total_component_allocations['CC'] += callocation
        if cvariant.startswith('CD'):
            total_component_allocations['CD'] += callocation
        if cvariant.startswith('CE'):
            total_component_allocations['CE'] += callocation

    for ccomponent, ctotal_allocation in total_component_allocations.items():
        assert ctotal_allocation <= space_available, f'You are allocating more than {space_available} units for variants of component {ccomponent}'

    for cvariant, creorder_point in reorder_points.items():
        assert reorder_points[cvariant] < inventory_allocations[cvariant], f'Reorder point must be less than inventory allocation for {cvariant}'
        assert reorder_points[cvariant] >= 0, f'Reorder point must be greater than or equal to zero for {cvariant}'


    component_variants = production_data.group_by(
        'day'
    ).agg(
        pl.col('CA'),
        pl.col('CB'),
        pl.col('CC'),
        pl.col('CD'),
        pl.col('CE'),
    ).sort(
        'day'
    ).to_pandas().set_index(
        'day'
    ).to_dict(orient='index')

    repair_wage_rate = 45
    tugger_wage_rate = 30

    repair_times = {
        'CA': 10,
        'CB': 8,
        'CC': 12,
        'CD': 4,
        'CE': 8,
    }

    all_metrics = []
    for day in tqdm(range(day_start, day_end + 1), f'Simulating {day_end + 1 -day_start} days'):
        day_vehicle_count = len(component_variants[day]['CA'])
        minutes_available = 960

        arrival_random_numbers = np.random.uniform(
            low=0.4,
            high=0.6,
            size=day_vehicle_count,
        )
        arrival_random_numbers_cumsum = arrival_random_numbers.cumsum()
        arrival_random_numbers_cumsum_normalized = (
            arrival_random_numbers_cumsum/arrival_random_numbers_cumsum.max()
        )
        arrival_times = minutes_available*arrival_random_numbers_cumsum_normalized

        vehicle_info_zip = zip(
            arrival_times,
            component_variants[day]['CA'],
            component_variants[day]['CB'],
            component_variants[day]['CC'],
            component_variants[day]['CD'],
            component_variants[day]['CE'],
        )

        vehicle_information = {}
        for vehicle, (arrival_time, CA, CB, CC, CD, CE) in enumerate(vehicle_info_zip, 1):
            vehicle_information[vehicle] = {
                'arrival_time': float(arrival_time),
                'CA': CA,
                'CB': CB,
                'CC': CC,
                'CD': CD,
                'CE': CE,
            }

        metrics_dict = {
            'CA_repairs': 0,
            'CB_repairs': 0,
            'CC_repairs': 0,
            'CD_repairs': 0,
            'CE_repairs': 0,
        }

        # Setup the simulation environment
        env = simpy.Environment()

        # Create resources for each station (assuming each station can handle one item at a time)
        stations = {f'Station {idx}': simpy.Resource(env, capacity=1) for idx in range(1, 6)}
        handlers = simpy.Resource(env, capacity=num_handlers)

        # Create the production system
        production_system = ProductionSystem(
            env,
            handlers=handlers,
            stations=stations,
            component_assignments=component_assignments,
            inventory_allocations=inventory_allocations,
            reorder_points=reorder_points,
            metrics_dict=metrics_dict,
            seed=day,
        )

        # Generate arrivals based on interarrival times
        env.process(generate_arrivals(env, production_system, vehicle_information))

        # Run the simulation
        env.run()

        run_metrics = dict(metrics_dict)
        run_metrics.update({
            'day': day,
            'num_handlers': num_handlers,
        })
        run_metrics['CA_repair_costs'] = repair_wage_rate*((run_metrics['CA_repairs']*repair_times['CA'])/60)
        run_metrics['CB_repair_costs'] = repair_wage_rate*((run_metrics['CB_repairs']*repair_times['CB'])/60)
        run_metrics['CC_repair_costs'] = repair_wage_rate*((run_metrics['CC_repairs']*repair_times['CC'])/60)
        run_metrics['CD_repair_costs'] = repair_wage_rate*((run_metrics['CD_repairs']*repair_times['CD'])/60)
        run_metrics['CE_repair_costs'] = repair_wage_rate*((run_metrics['CE_repairs']*repair_times['CE'])/60)
        run_metrics['MH_costs'] = (minutes_available/60)*run_metrics['num_handlers']*tugger_wage_rate
        run_metrics['Total_repair_costs'] = (
            run_metrics['CA_repair_costs']
            + run_metrics['CB_repair_costs']
            + run_metrics['CC_repair_costs']
            + run_metrics['CD_repair_costs']
            + run_metrics['CE_repair_costs']
        )
        run_metrics['Total_costs'] = run_metrics['MH_costs'] + run_metrics['Total_repair_costs']

        all_metrics.append(dict(run_metrics))

    return all_metrics

"""The following code block reads the production data and prints the first five rows."""

data = pl.read_csv('https://raw.githubusercontent.com/nkfreeman/2024_IDA_Hackathon/refs/heads/main/production_data.csv')
data.head()

"""The following code block calculates our initial solution."""

columns = ['CA', 'CB', 'CC', 'CD', 'CE'] # List of components

num_handlers = 1 # number of handlers
station_capacity = 100 # station capacity

# Repair cost per component
repair_times = {
    'CA': 10,
    'CB': 8,
    'CC': 12,
    'CD': 4,
    'CE': 8,
}

# Number of variants per component
num_variants = {
    'CA': 8,
    'CB': 3,
    'CC': 7,
    'CD': 6,
    'CE': 9,
}

# Compute station assignment by a scoring system
placement_scores = {}
for key in columns:
    placement_scores[key] = repair_times[key] * num_variants[key]
sorted_keys = sorted(placement_scores, key=placement_scores.get, reverse=True)
component_assignments = {
    'Station 1': sorted_keys[0],
    'Station 2': sorted_keys[1],
    'Station 3': sorted_keys[2],
    'Station 4': sorted_keys[3],
    'Station 5': sorted_keys[4],
}

# Figure out inventory allocation based on expected variant demand
variant_percentages = {}
for component in columns:
    counts = data[component].value_counts()
    total = counts['count'].sum()
    percentages = (counts['count'] / total * station_capacity).to_list()
    variant_percentages[component] = {counts[component][i]: round(percentages[i]) for i in range(len(counts))}

for component in columns:
    total_percentage = sum(variant_percentages[component].values())
    if total_percentage > station_capacity:
        diff = total_percentage - station_capacity
        max_component = max(variant_percentages[component], key=variant_percentages[component].get)
        variant_percentages[component][max_component] -= diff
    if total_percentage < station_capacity:
        diff = station_capacity - total_percentage
        min_component = min(variant_percentages[component], key=variant_percentages[component].get)
        variant_percentages[component][min_component] += diff
inventory_allocations = {key: value for d in variant_percentages.values() for key, value in d.items()}

# Maximize reorder points so handlers keep moving
reorder_points = {key: value - 1 for key, value in inventory_allocations.items()}

"""The following code block simulates the initial solution over the 90 days of production data."""

simulation_metrics = run_simulation(
    production_data=data,
    component_assignments=component_assignments,
    inventory_allocations=inventory_allocations,
    reorder_points=reorder_points,
    num_handlers=num_handlers,
    day_start=1,
    day_end=90,
    space_available=station_capacity,
)

"""The following code block graphs the results of the initial solution."""

simulation_metrics = pd.DataFrame(simulation_metrics)
columns_to_include = ['day', 'MH_costs', 'Total_repair_costs', 'Total_costs']

fig, ax = plt.subplots(1, 1, figsize=(10, 4))
simulation_metrics[columns_to_include].set_index(
    'day'
).plot(
    ax=ax
)
ax.spines[['right', 'top']].set_visible(False)
ax.legend(bbox_to_anchor=(1.01, 1.01))
plt.show()

print(simulation_metrics['Total_costs'].sum()) # total cost of initial solution

"""The next code blocks define functions used for optimization."""

def compute_total_cost(simulation_metrics):
    """Compute the total cost from the simulation results."""
    simulation_df = pd.DataFrame(simulation_metrics)
    total_cost = simulation_df['Total_costs'].sum()
    return total_cost

def optimize_inventory(inventory_allocations, reorder_points, data, component_assignments, space_available, max_iterations=5000):
    best_inventory_allocations = inventory_allocations.copy()
    best_reorder_points = reorder_points.copy()

    # Initial total cost
    simulation_metrics = run_simulation(
        production_data=data,
        component_assignments=component_assignments,
        inventory_allocations=best_inventory_allocations,
        reorder_points=best_reorder_points,
        num_handlers=num_handlers,  # You can optimize handlers separately
        day_start=1,
        day_end=90,
        space_available=space_available,
    )
    best_total_cost = compute_total_cost(simulation_metrics)

    # Optimization loop (using a form of stochastic search or simulated annealing)
    for iteration in range(max_iterations):
        # Generate a neighbor solution
        new_inventory_allocations, new_reorder_points = get_neighbor_solution(best_inventory_allocations, best_reorder_points)

        # Run the simulation for the new solution
        new_simulation_metrics = run_simulation(
            production_data=data,
            component_assignments=component_assignments,
            inventory_allocations=new_inventory_allocations,
            reorder_points=new_reorder_points,
            num_handlers=num_handlers,  # You can also make this dynamic
            day_start=1,
            day_end=90,
            space_available=space_available,
        )

        # Compute the new total cost
        new_total_cost = compute_total_cost(new_simulation_metrics)

        # Accept the new solution if it's better (you can add probabilistic acceptance to make it simulated annealing)
        if new_total_cost < best_total_cost:
            best_inventory_allocations = new_inventory_allocations
            best_reorder_points = new_reorder_points
            best_total_cost = new_total_cost
            print(f"Iteration {iteration}: Improved cost to {best_total_cost}")

    return best_inventory_allocations, best_reorder_points, best_total_cost, new_simulation_metrics

def get_neighbor_solution(inventory_allocations, reorder_points):
    """Generate a neighbor solution by tweaking inventory allocations or reorder points."""
    new_inventory_allocations = inventory_allocations.copy()
    new_reorder_points = reorder_points.copy()

    # Randomly select an inventory items to modify
    random_item1, random_item2 = 1, 1
    while random_item1 == random_item2:
      random_item1 = random.choice(list(inventory_allocations.keys()))
      random_item2 = random.choice([x for x in list(inventory_allocations.keys()) if x[:2] == random_item1[:2]])

      #increase one while decreasing other
    if new_inventory_allocations[random_item2] > 1:
        new_reorder_points[random_item1] += 1
        new_reorder_points[random_item2] -= 1
        new_inventory_allocations[random_item1] += 1
        new_inventory_allocations[random_item2] -= 1



    return new_inventory_allocations, new_reorder_points

"""The following code block performs optimization on the initial solution. It iis only set to 10 iterations here, but it would need to be increased to see a significant performance increase."""

# Initialize your inventory allocations and reorder points
initial_inventory_allocations = inventory_allocations  # Use your existing allocations
initial_reorder_points = reorder_points  # Use your existing reorder points

# Run the optimization process
best_allocations, best_reorder_points, best_cost, best_simulation_metric = optimize_inventory(
    initial_inventory_allocations,
    initial_reorder_points,
    data=data,  # Your dataset
    component_assignments=component_assignments,  # Your current component assignments
    space_available=station_capacity,  # Available space in inventory
    max_iterations=10  # Number of iterations for the optimization
)

print(f"Best total cost: {best_cost}")
print(f"Optimized inventory allocations: {best_allocations}")
print(f"Optimized reorder points: {best_reorder_points}")

"""The following code block contains our hard-coded final solution for capacity 100."""

component_assignments = {
    'Station 1': 'CA',
    'Station 2': 'CC',
    'Station 3': 'CE',
    'Station 4': 'CB',
    'Station 5': 'CD'
}

inventory_allocations = {
    'CA1': 15,
    'CA2': 13,
    'CA3': 7,
    'CA4': 14,
    'CA5': 9,
    'CA6': 16,
    'CA7': 11,
    'CA8': 15,
    'CC1': 5,
    'CC2': 22,
    'CC3': 10,
    'CC4': 15,
    'CC5': 12,
    'CC6': 19,
    'CC7': 17,
    'CE1': 2,
    'CE2': 7,
    'CE3': 12,
    'CE4': 5,
    'CE5': 2,
    'CE6': 18,
    'CE7': 13,
    'CE8': 18,
    'CE9': 23,
    'CB1': 16,
    'CB2': 57,
    'CB3': 27,
    'CD1': 9,
    'CD2': 17,
    'CD3': 35,
    'CD4': 2,
    'CD5': 22,
    'CD6': 15
}

reorder_points = {key: value - 1 for key, value in inventory_allocations.items()}

simulation_metrics = run_simulation(
    production_data=data,
    component_assignments=component_assignments,
    inventory_allocations=inventory_allocations,
    reorder_points=reorder_points,
    num_handlers=num_handlers,
    day_start=1,
    day_end=90,
    space_available=100,
)

simulation_metrics = pd.DataFrame(simulation_metrics)
columns_to_include = ['day', 'MH_costs', 'Total_repair_costs', 'Total_costs']

fig, ax = plt.subplots(1, 1, figsize=(10, 4))
simulation_metrics[columns_to_include].set_index(
    'day'
).plot(
    ax=ax
)
ax.spines[['right', 'top']].set_visible(False)
ax.legend(bbox_to_anchor=(1.01, 1.01))
plt.show()

print(simulation_metrics['Total_costs'].sum()) # total cost of final solution

"""The following code block contains our hard-coded *optimal* solution for capacity 140. We believe our optimization methods can find an optimal solution for a smaller capacity than 140, but we haven't had time to try."""

component_assignments = {
    'Station 1': 'CC',
    'Station 2': 'CA',
    'Station 3': 'CE',
    'Station 4': 'CB',
    'Station 5': 'CD'
}

inventory_allocations = {
    'CC1': 7,
    'CC2': 33,
    'CC3': 13,
    'CC4': 21,
    'CC5': 15,
    'CC6': 27,
    'CC7': 24,
    'CA1': 22,
    'CA2': 17,
    'CA3': 10,
    'CA4': 20,
    'CA5': 11,
    'CA6': 22,
    'CA7': 15,
    'CA8': 23,
    'CE1': 4,
    'CE2': 9,
    'CE3': 17,
    'CE4': 7,
    'CE5': 4,
    'CE6': 24,
    'CE7': 17,
    'CE8': 25,
    'CE9': 33,
    'CB1': 17,
    'CB2': 91,
    'CB3': 32,
    'CD1': 12,
    'CD2': 24,
    'CD3': 53,
    'CD4': 4,
    'CD5': 29,
    'CD6': 18,
}

reorder_points = {key: value - 1 for key, value in inventory_allocations.items()}

simulation_metrics = run_simulation(
    production_data=data,
    component_assignments=component_assignments,
    inventory_allocations=inventory_allocations,
    reorder_points=reorder_points,
    num_handlers=num_handlers,
    day_start=1,
    day_end=90,
    space_available=140,
)

simulation_metrics = pd.DataFrame(simulation_metrics)
columns_to_include = ['day', 'MH_costs', 'Total_repair_costs', 'Total_costs']

fig, ax = plt.subplots(1, 1, figsize=(10, 4))
simulation_metrics[columns_to_include].set_index(
    'day'
).plot(
    ax=ax
)
ax.spines[['right', 'top']].set_visible(False)
ax.legend(bbox_to_anchor=(1.01, 1.01))
plt.show()

print(simulation_metrics['Total_costs'].sum()) # total cost of final solution