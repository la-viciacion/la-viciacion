// Why a library entry cannot be marked as completed (the API decides, this only words it).

/** `entry.complete_blocked` -> message for the player, or '' when it can be completed. */
export function blockedReason(entry, currentSeason) {
  switch (entry.complete_blocked) {
    case 'closed_season':
      return `Temporada ${entry.season} cerrada: solo se pueden completar juegos de la temporada actual (${currentSeason}).`;
    case 'completed_in_season':
      return 'Ya lo has completado esta temporada en otra plataforma.';
    default:
      return '';
  }
}
