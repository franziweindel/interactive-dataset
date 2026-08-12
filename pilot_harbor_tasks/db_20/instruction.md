You are interacting with a MySQL database. You can execute SQL queries by calling the `execute_sql` tool with your query. When you have determined the answer, call the `submit_answer` tool with your final answer.

Question: Which bond type accounted for the majority of the bonds found in molecule TR018 and state whether or not this molecule is carcinogenic?
There are 2 tables involved with this task. The name of the 1st table is bond, and the headers of this table are bond_id,molecule_id,bond_type. The name of the 2nd table is molecule, and the headers of this table are molecule_id,label.