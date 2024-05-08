from flask import Flask, render_template, request
import pandas as pd
import requests
app = Flask(__name__)
def get_match_ids(puuid, mass_region, no_games, queue_id, api):
    api_url = (
       "https://" +
        mass_region +
        ".api.riotgames.com/lol/match/v5/matches/by-puuid/" +
        puuid +
        "/ids?start=0" +
        "&count=" +
        # Fetch 20 matches to account for filtration later on
        str(no_games * 2) +  
        "&queue=" +
        str(queue_id) +
        "&api_key=" +
        api
    )
    resp = requests.get(api_url)
    match_ids = resp.json()
    # the following code filters out matches less than 10 minutes as requested by test user; 
    #matches that are remade contain statistics that my test user does not consider necessary as 
    #they will skew data and not provide accurate results in the tables
    filtered_match_ids = []
    for match_id in match_ids:
        match_data = get_match_data(match_id, mass_region, api)
        match_duration = match_data['info']['gameDuration']
        if match_duration >= 600:
            filtered_match_ids.append(match_id)
        if len(filtered_match_ids) >= no_games:
            break
    return filtered_match_ids[:no_games]


def get_match_data(match_id, mass_region, api):
    api_url = (
        "https://" +
        mass_region +
        ".api.riotgames.com/lol/match/v5/matches/" +
        match_id +
        "?api_key=" +
        api
    )
    resp = requests.get(api_url)
    match_data = resp.json()
    return match_data
def find_player_data(match_data, puuid):
    participants = match_data['metadata']['participants']
    player_index = participants.index(puuid)
    player_data = match_data['info']['participants'][player_index]
    return player_data

def gather_all_data(puuid, match_ids, mass_region, api):
    data = {
        'champion': [],
        'kills': [],
        'deaths': [],
        'assists': [],
        'win': [],
        'count': [],  
        'items': []   
    }

    for match_id in match_ids:
        match_data = get_match_data(match_id, mass_region, api)
        player_data = find_player_data(match_data, puuid)
        if all(f'item{i}' not in player_data for i in range(7)):
            continue

        champion = player_data['championName']
        k = player_data['kills']
        d = player_data['deaths']
        a = player_data['assists']
        win = player_data['win']
        items = [player_data[f'item{i}'] for i in range(7) if f'item{i}' in player_data]

        data['champion'].append(champion)
        data['kills'].append(k)
        data['deaths'].append(d)
        data['assists'].append(a)
        data['win'].append(win)
        data['count'].append(1) 
        data['items'].append(items) 

    df = pd.DataFrame(data)

    return df
def fetch_item_image_urls():
    version_response = requests.get('https://ddragon.leagueoflegends.com/api/versions.json')
    version = version_response.json()[0]  
    
    item_url = f'https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/item.json'
    item_response = requests.get(item_url)
    item_data = item_response.json()['data']
    
    item_image_urls = {}
    for item_id, item_info in item_data.items():

        item_image_url = f"https://ddragon.leagueoflegends.com/cdn/{version}/img/item/{item_id}.png"
        item_image_urls[item_info['name']] = item_image_url
    
    return item_image_urls

def fetch_champion_image_urls():
    version_response = requests.get('https://ddragon.leagueoflegends.com/api/versions.json')
    version = version_response.json()[0]  
    
    champion_url = f'https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json'
    champion_response = requests.get(champion_url)
    champion_data = champion_response.json()['data']
    
    champion_image_urls = {}
    for champion_name, champion_info in champion_data.items():
      
        champion_image_url = f"https://ddragon.leagueoflegends.com/cdn/{version}/img/champion/{champion_info['image']['full']}"
        champion_image_urls[champion_name] = champion_image_url
    
    return champion_image_urls
def calculate_item_win_rate(df):
    item_win_rates = {}
    for index, row in df.iterrows():
        items = row['items']
        win = row['win']
        for item in items:
            if item not in item_win_rates:
                item_win_rates[item] = {'total': 0, 'wins': 0}
            item_win_rates[item]['total'] += 1
            if win:
                item_win_rates[item]['wins'] += 1

    for item, rates in item_win_rates.items():
        if rates['total'] > 0:
            item_win_rates[item]['win_rate'] = round((rates['wins'] / rates['total']) * 100, 2)
        else:
            item_win_rates[item]['win_rate'] = 0
    return item_win_rates
def fetch_item_data():
    version_response = requests.get('https://ddragon.leagueoflegends.com/api/versions.json')
    version = version_response.json()[0] 
    item_url = f'https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/item.json'
    item_response = requests.get(item_url)
    item_data = item_response.json()['data']
    item_id_to_name = {}
    for item_id, item_info in item_data.items():
        item_id_to_name[int(item_id)] = item_info['name']
    return item_id_to_name
def get_match_timeline(match_id, mass_region, api):
    timeline_url = (
        f"https://{mass_region}.api.riotgames.com/lol/match/v5/matches/{match_id}/timeline?api_key={api}"
    )
    timeline_response = requests.get(timeline_url)
    timeline_data = timeline_response.json()
    return timeline_data
def get_cs_at_minutes(timeline_data, participant_id):
    cs_counts = {10: None, 20: None, 30: None}
    for frame in timeline_data['info']['frames']:
        minute = frame['timestamp'] // 60000 
        if minute in cs_counts:
            participant_frame = frame['participantFrames'][str(participant_id)]
            cs_counts[minute] = participant_frame['minionsKilled'] + participant_frame.get('jungleMinionsKilled', 0)
    return [cs_counts[minute] for minute in sorted(cs_counts.keys())]
def aggregate_cs_data_for_top_lane(puuid, match_ids, mass_region, api):
    champion_cs_data = {}
    for match_id in match_ids:
        match_data = get_match_data(match_id, mass_region, api)
        timeline_data = get_match_timeline(match_id, mass_region, api)
        player_data = find_player_data(match_data, puuid)
        if player_data['individualPosition'].upper() == 'TOP':
            champion_name = player_data['championName']
            participant_id = player_data['participantId']
            cs_at_minutes = get_cs_at_minutes(timeline_data, participant_id)
            if champion_name not in champion_cs_data:
                champion_cs_data[champion_name] = []
            champion_cs_data[champion_name].append(cs_at_minutes)
    for champion, cs_lists in champion_cs_data.items():
        cs_averages = pd.DataFrame(cs_lists).mean().tolist()
        champion_cs_data[champion] = cs_averages
    return champion_cs_data
def find_enemy_laner(match_data, player_lane):
    enemy_laner = None
    participants = match_data['info']['participants']
    for participant in participants:
        if participant['individualPosition'] == player_lane and participant["teamId"] != 100:
                enemy_laner = participant['championName']
                break
    if enemy_laner != None:
        return enemy_laner
def calculate_top_lane_win_rates(puuid, match_ids, mass_region, api):
    champion_pairs = {}
    for match_id in match_ids:
        match_data = get_match_data(match_id, mass_region, api)
        player_data = find_player_data(match_data, puuid)
        champion_name = player_data['championName']
        if player_data['individualPosition'].upper() == 'TOP':
            win_status = player_data['win']
            enemy_champion_name = find_enemy_laner(match_data, 'TOP') 
            if champion_name not in champion_pairs:
                champion_pairs[champion_name] = {}
            if enemy_champion_name not in champion_pairs[champion_name]:
                champion_pairs[champion_name][enemy_champion_name] = {'total': 0, 'wins': 0}
                
            champion_pairs[champion_name][enemy_champion_name]['total'] += 1
            if win_status:
                champion_pairs[champion_name][enemy_champion_name]['wins'] += 1
    for champion, enemy_data in champion_pairs.items():
        for enemy_champion, win_data in enemy_data.items():
            total_games = win_data['total']
            if total_games > 0:
                win_rate = (win_data['wins'] / total_games) * 100
            else:
                win_rate = 0
            champion_pairs[champion][enemy_champion] = win_rate
    return champion_pairs
def calculate_win_rates_against_all_champions(puuid, match_ids, mass_region, api):
    champion_win_rates = {}

    for match_id in match_ids:
        match_data = get_match_data(match_id, mass_region, api)
        player_data = find_player_data(match_data, puuid)
        if player_data:
            win_status = player_data['win']
            enemy_champions = [participant['championName'] for participant in match_data['info']['participants'] if participant['puuid'] != puuid]
            
            for enemy_champion in enemy_champions:
                if enemy_champion not in champion_win_rates:
                    champion_win_rates[enemy_champion] = {'total': 0, 'wins': 0}

                champion_win_rates[enemy_champion]['total'] += 1
                if win_status:
                    champion_win_rates[enemy_champion]['wins'] += 1
    for enemy_champion, win_data in champion_win_rates.items():
        total_games = win_data['total']
        if total_games > 0:
            win_rate = (win_data['wins'] / total_games) * 100
        else:
            win_rate = 0
        champion_win_rates[enemy_champion] = win_rate

    return champion_win_rates
def get_top_lane_stats(puuid, mass_region, api, match_ids):
    top_lane_stats = {}
    for match_id in match_ids:
        match_data = get_match_data(match_id, mass_region, api)
        for participant in match_data['info']['participants']:
            if participant['puuid'] == puuid and participant['individualPosition'].upper() == 'TOP':
                champion_name = participant['championName']
                if champion_name not in top_lane_stats:
                    top_lane_stats[champion_name] = {
                        'gold_earned': 0,
                        'damage_dealt': 0,
                        'damage_taken': 0,
                        'count': 0
                    }
                top_lane_stats[champion_name]['gold_earned'] += participant['goldEarned']
                top_lane_stats[champion_name]['damage_dealt'] += participant['totalDamageDealtToChampions']
                top_lane_stats[champion_name]['damage_taken'] += participant['totalDamageTaken']
                top_lane_stats[champion_name]['count'] += 1
    for champion, stats in top_lane_stats.items():
        count = stats['count']
        top_lane_stats[champion]['gold_earned'] /= count
        top_lane_stats[champion]['damage_dealt'] /= count
        top_lane_stats[champion]['damage_taken'] /= count
    return top_lane_stats
def get_summoner_rank_and_lp(summonerId, region, api):
    api_url = f"https://{region}.api.riotgames.com/lol/league/v4/entries/by-summoner/{summonerId}?api_key={api}"
    resp = requests.get(api_url)
    leagues = resp.json()
    for league in leagues:
        if league['queueType'] == 'RANKED_SOLO_5x5':
            print (league['tier'], league['rank'], league['leaguePoints'])
            return league['tier'], league['rank'], league['leaguePoints']
    return None, None, 0
import pandas as pd
summoner_name = "4IDFreecc"
region = "ph2"
no_games = 10    
type = "normal"
queue_id = 420
mass_region = "SEA"
api = "RGAPI-6ccfd4fa-2427-4b68-a667-032a99327b71"
puuid = "NjeWMU0CD4kv-1r2nR3QijOa_w_rJ4uJyymGl7WrXaBZs4asE4kIAlOyK-va-XYV94fl0j4J4mye7A"
match_ids = get_match_ids(puuid, mass_region, no_games, queue_id, api)
df = gather_all_data(puuid, match_ids, mass_region, api)
champ_df = df.groupby('champion').agg({'kills': 'mean', 'deaths': 'mean', 'assists': 'mean', 'win': 'mean', 'count': 'sum'})
champ_df.reset_index(inplace=True)
champ_df = champ_df[champ_df['count'] >= 2]
champ_df['kda'] = (champ_df['kills'] + champ_df['assists']) / champ_df['deaths']
champ_df = champ_df.sort_values('kda', ascending=False)

best_row = champ_df.iloc[0]
worst_row = champ_df.iloc[-1]
bestchamp = best_row['champion']
worstchamp = worst_row['champion']
bestkda = round(best_row['kda'],2)
worstkda = round(worst_row['kda'],2)
bestcount = best_row['count']
worstcount = worst_row['count']


champ_df = champ_df.sort_values('count', ascending=False)
most_played_row = champ_df.iloc[0]
mostplayedchamp = most_played_row['champion']
mostplayedcount = most_played_row['count']
win_rate = str(round(most_played_row['win'] * 100, 1)) + "%"
mostplayedwinrate = win_rate
highest_kill_row = df.sort_values('kills', ascending=False).iloc[0]
highestkillchamp = highest_kill_row['champion']
highestkillkills = round((highest_kill_row['kills']), 2)
filtered_df = df[['champion', 'kills', 'deaths','assists']]
item_win_rates = calculate_item_win_rate(df)
item_id_to_name = fetch_item_data()
champion_image_urls = fetch_champion_image_urls()
item_image_urls = fetch_item_image_urls()
item_win_rates_dict_with_names = {}
for item_id, rates in item_win_rates.items():
    item_name = item_id_to_name.get(item_id)
    if item_name is not None:
        item_win_rates_dict_with_names[item_name] = rates
cs_data = aggregate_cs_data_for_top_lane(puuid, match_ids, "SEA", api)
top_lane_win_rates = calculate_top_lane_win_rates(puuid, match_ids, mass_region, api)
win_rates_against_all_champions = calculate_win_rates_against_all_champions(puuid, match_ids, mass_region, api)
top_lane_stats = get_top_lane_stats(puuid, mass_region, api, match_ids)
@app.route('/')
def render_stats_template():
    return render_template('index.html', summoner_name=summoner_name, region=region, no_games=no_games,
                           bestchamp=bestchamp, worstchamp=worstchamp, bestkda=bestkda, worstkda=worstkda,
                           bestcount=bestcount, worstcount=worstcount,
                           mostplayedchamp=mostplayedchamp, mostplayedcount=mostplayedcount,
                           mostplayedwinrate=mostplayedwinrate,
                           win_rate=win_rate, highestkillchamp=highestkillchamp, highestkillkills=highestkillkills, df=filtered_df.to_html(index=False, classes=['sortable']),
                           item_win_rates_dict_with_names=item_win_rates_dict_with_names, cs_data=cs_data, item_image_urls=item_image_urls, champion_image_urls=champion_image_urls,
                           top_lane_win_rates=top_lane_win_rates, win_rates_against_all_champions=win_rates_against_all_champions, top_lane_stats=top_lane_stats)
@app.route('/performancehighlights')
def performancehighlights():
    return render_template('performancehighlights.html', summoner_name=summoner_name, region=region, no_games=no_games,
                           bestchamp=bestchamp, worstchamp=worstchamp, bestkda=bestkda, worstkda=worstkda,
                           bestcount=bestcount, worstcount=worstcount,
                           mostplayedchamp=mostplayedchamp, mostplayedcount=mostplayedcount,
                           mostplayedwinrate=mostplayedwinrate,
                           win_rate=win_rate, highestkillchamp=highestkillchamp, highestkillkills=highestkillkills, df=filtered_df.to_html(index=False, classes=['sortable']),
                           item_win_rates_dict_with_names=item_win_rates_dict_with_names, cs_data=cs_data, item_image_urls=item_image_urls, champion_image_urls=champion_image_urls,
                           )
@app.route('/itemwinrates')
def itemwinrates():
    return render_template('itemwinrates.html', summoner_name=summoner_name, region=region, no_games=no_games,
                           bestchamp=bestchamp, worstchamp=worstchamp, bestkda=bestkda, worstkda=worstkda,
                           bestcount=bestcount, worstcount=worstcount,
                           mostplayedchamp=mostplayedchamp, mostplayedcount=mostplayedcount,
                           mostplayedwinrate=mostplayedwinrate,
                           win_rate=win_rate, highestkillchamp=highestkillchamp, highestkillkills=highestkillkills, df=filtered_df.to_html(index=False, classes=['sortable']),
                           item_win_rates_dict_with_names=item_win_rates_dict_with_names, cs_data=cs_data, item_image_urls=item_image_urls, champion_image_urls=champion_image_urls,
                           )
@app.route('/averagecs')
def averagecs():
    return render_template('averagecs.html', summoner_name=summoner_name, region=region, no_games=no_games,
                           bestchamp=bestchamp, worstchamp=worstchamp, bestkda=bestkda, worstkda=worstkda,
                           bestcount=bestcount, worstcount=worstcount,
                           mostplayedchamp=mostplayedchamp, mostplayedcount=mostplayedcount,
                           mostplayedwinrate=mostplayedwinrate,
                           win_rate=win_rate, highestkillchamp=highestkillchamp, highestkillkills=highestkillkills, df=filtered_df.to_html(index=False, classes=['sortable']),
                           item_win_rates_dict_with_names=item_win_rates_dict_with_names, cs_data=cs_data, item_image_urls=item_image_urls, champion_image_urls=champion_image_urls,
                           )
@app.route('/winrates')
def winrates():
    return render_template('winrates.html', summoner_name=summoner_name, region=region, no_games=no_games,
                           bestchamp=bestchamp, worstchamp=worstchamp, bestkda=bestkda, worstkda=worstkda,
                           bestcount=bestcount, worstcount=worstcount,
                           mostplayedchamp=mostplayedchamp, mostplayedcount=mostplayedcount,
                           mostplayedwinrate=mostplayedwinrate,
                           win_rate=win_rate, highestkillchamp=highestkillchamp, highestkillkills=highestkillkills, df=filtered_df.to_html(index=False, classes=['sortable']),
                           item_win_rates_dict_with_names=item_win_rates_dict_with_names, cs_data=cs_data, item_image_urls=item_image_urls, champion_image_urls=champion_image_urls,
                           top_lane_win_rates=top_lane_win_rates, win_rates_against_all_champions=win_rates_against_all_champions)
@app.route('/TopStats')
def TopStats():
    return render_template('TopStats.html', summoner_name=summoner_name, region=region, no_games=no_games,
                           bestchamp=bestchamp, worstchamp=worstchamp, bestkda=bestkda, worstkda=worstkda,
                           bestcount=bestcount, worstcount=worstcount,
                           mostplayedchamp=mostplayedchamp, mostplayedcount=mostplayedcount,
                           mostplayedwinrate=mostplayedwinrate,
                           win_rate=win_rate, highestkillchamp=highestkillchamp, highestkillkills=highestkillkills, df=filtered_df.to_html(index=False, classes=['sortable']),
                           item_win_rates_dict_with_names=item_win_rates_dict_with_names, cs_data=cs_data, item_image_urls=item_image_urls, champion_image_urls=champion_image_urls,
                           top_lane_win_rates=top_lane_win_rates, win_rates_against_all_champions=win_rates_against_all_champions, top_lane_stats=top_lane_stats)
if __name__ == '__main__':
    app.run(host='localhost', port=5000, debug=False)
